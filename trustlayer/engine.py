"""Agent loop, retry strategies, and Cathedral orchestrator."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from trustlayer.auth import AuthToken
from trustlayer.types import Action, Update
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
    and retries up to `retry.max_attempts` times on failure.
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
        delay = self.retry.base_delay

        for attempt in range(1, self.retry.max_attempts + 1):
            logger.debug("Attempt %d/%d for goal: %s", attempt, self.retry.max_attempts, goal)

            proposal = await self.agent.propose(goal)
            action = parse_action(proposal)

            if not action:
                logger.warning("Attempt %d: unparseable proposal", attempt)
                last_event = ValidationEvent(
                    success=False,
                    description=goal,
                    failed_constraint="unparseable proposal",
                )
            else:
                update = Update(description=goal, actions=[action], token=token)
                last_event = self.validator.validate_update(update)
                logger.info("Attempt %d: %s", attempt, last_event)

            if last_event.success:
                return last_event

            if attempt < self.retry.max_attempts:
                await asyncio.sleep(delay)
                delay *= self.retry.backoff_factor

        return last_event  # type: ignore[return-value]
