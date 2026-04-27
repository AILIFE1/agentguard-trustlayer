"""Agent loop, retry strategies, Cathedral orchestrator, and GuardedAgent API."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets as _secrets
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from trustlayer.auth import AuthorityLevel, AuthToken
from trustlayer.constraints import Constraint
from trustlayer.types import Action, State, Update
from trustlayer.validator import ValidationEvent, Validator

logger = logging.getLogger("trustlayer.engine")

AsyncModel = Callable[[str], Awaitable[str]]


@dataclass
class RetryConfig:
    """Controls how Cathedral retries failed proposals."""

    max_attempts: int = 3
    base_delay: float = 0.5
    backoff_factor: float = 2.0


class Agent:
    """Thin wrapper around an async LLM callable."""

    def __init__(self, model: AsyncModel):
        self.model = model

    async def propose(self, prompt: str) -> str:
        return await self.model(prompt)


def parse_action(text: str) -> Optional[Action]:
    """Parse a JSON string into an Action, returning None on any error."""
    try:
        data = json.loads(text)
        return Action(data["type"], data["target"], data.get("value"))
    except Exception:
        return None


class Cathedral:
    """Orchestrates an Agent against a Validator with optional retry.

    Each call to `step` proposes one action from the agent, validates it,
    and retries up to `retry.max_attempts` times on failure.  The reason
    for the last failure is appended to the prompt on each retry so the
    model can self-correct.
    """

    def __init__(
        self,
        validator: Validator,
        agent: Agent,
        retry: Optional[RetryConfig] = None,
    ):
        self.validator = validator
        self.agent = agent
        self.retry = retry or RetryConfig()

    async def step(self, goal: str, token: AuthToken) -> ValidationEvent:
        """Run one goal-cycle, retrying on parse or validation failure.

        Returns the final ValidationEvent (success or last failure).
        """
        last_event: Optional[ValidationEvent] = None
        last_error = ""
        delay = self.retry.base_delay

        for attempt in range(1, self.retry.max_attempts + 1):
            logger.debug("Attempt %d/%d for goal: %s", attempt, self.retry.max_attempts, goal)

            prompt = f"{goal}\nLast error: {last_error}" if last_error else goal
            proposal = await self.agent.propose(prompt)
            action = parse_action(proposal)

            if not action:
                logger.warning("Attempt %d: unparseable proposal", attempt)
                last_error = "unparseable proposal"
                last_event = ValidationEvent(
                    success=False,
                    description=goal,
                    failed_constraint=last_error,
                )
            else:
                update = Update(description=goal, actions=[action], token=token)
                last_event = self.validator.validate_update(update)
                last_error = last_event.failed_constraint or ""
                logger.info("Attempt %d: %s", attempt, last_event)

            if last_event.success:
                return last_event

            if attempt < self.retry.max_attempts:
                await asyncio.sleep(delay)
                delay *= self.retry.backoff_factor

        return last_event  # type: ignore[return-value]


class GuardedAgent:
    """High-level API: bundles State, Validator, Agent, and Cathedral into one object.

    Example::

        agent = GuardedAgent(
            model=my_async_llm,
            rules=[LambdaConstraint("balance <= 1000", lambda v: v["balance"] <= 1000)],
            initial_state={"balance": 100},
        )
        result = await agent.run("Set balance to 500")
    """

    def __init__(
        self,
        model: AsyncModel,
        rules: List[Constraint],
        initial_state: Dict[str, Any],
        ttl_seconds: int = 3600,
        retry: Optional[RetryConfig] = None,
    ):
        self._secret = _secrets.token_bytes(32)
        self.state = State(initial_state)
        self.validator = Validator(self.state, rules, self._secret)
        self.agent = Agent(model)
        self.engine = Cathedral(self.validator, self.agent, retry=retry)
        self.token = AuthToken.issue(
            AuthorityLevel.USER, "agent", ttl_seconds, self._secret
        )

    async def run(self, goal: str) -> Dict[str, Any]:
        """Run *goal* and return a result dict with status, state, and audit hash."""
        event = await self.engine.step(goal, self.token)
        if event.success:
            return {
                "status": "success",
                "state": self.state.values,
                "audit": event.audit_hash,
            }
        return {
            "status": "blocked",
            "reason": event.failed_constraint,
            "state": self.state.values,
        }
