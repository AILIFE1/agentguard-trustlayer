"""
TrustLayer demo  --  python examples/demo.py

Walk-through:
  1. Agent proposes an invalid update  -> REJECTED
  2. Agent retries with a valid update -> ACCEPTED
  3. State reflects the accepted change
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from trustlayer import (
    Action,
    Agent,
    AuthorityLevel,
    AuthToken,
    Cathedral,
    LambdaConstraint,
    RetryConfig,
    State,
    Update,
    Validator,
    ValidationEvent,
)

SECRET = b"demo-secret"

# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

score_in_range = LambdaConstraint(
    "score_in_range",
    lambda v: 0 <= v.get("score", 0) <= 100,
    priority=10,
)

mode_not_restricted = LambdaConstraint(
    "mode_not_restricted",
    lambda v: v.get("mode") != "restricted",
    priority=20,
)

# ---------------------------------------------------------------------------
# Mock model  (bad proposal first, valid proposal second)
# ---------------------------------------------------------------------------

_call = 0


async def mock_model(prompt: str) -> str:
    global _call
    _call += 1
    if _call == 1:
        return json.dumps({"type": "update", "target": "score", "value": 9999})
    return json.dumps({"type": "update", "target": "score", "value": 42})


# ---------------------------------------------------------------------------
# Custom Cathedral subclass that prints REJECTED / RETRYING / ACCEPTED
# ---------------------------------------------------------------------------

class LoggingCathedral(Cathedral):
    async def step(self, goal: str, token: AuthToken) -> ValidationEvent:
        delay = self.retry.base_delay

        for attempt in range(1, self.retry.max_attempts + 1):
            proposal = await self.agent.propose(goal)

            from trustlayer.engine import parse_action
            action = parse_action(proposal)

            if not action:
                print(f"  [REJECTED] unparseable proposal on attempt {attempt}")
                last_event = ValidationEvent(
                    success=False,
                    description=goal,
                    failed_constraint="unparseable proposal",
                )
            else:
                update = Update(description=goal, actions=[action], token=token)
                last_event = self.validator.validate_update(update)

                if last_event.success:
                    print(f"  [ACCEPTED] {goal} (attempt {attempt})")
                    return last_event
                else:
                    print(f"  [REJECTED] {goal} | constraint: {last_event.failed_constraint}")

            if attempt < self.retry.max_attempts:
                print(f"  [RETRYING] attempt {attempt + 1} of {self.retry.max_attempts}...")
                await asyncio.sleep(delay)
                delay *= self.retry.backoff_factor

        return last_event  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    global _call
    _call = 0

    print()
    print("=" * 52)
    print("  TrustLayer v2.0  --  Validation Demo")
    print("=" * 52)

    state = State(values={"score": 50, "mode": "normal"})
    validator = Validator(state, [score_in_range, mode_not_restricted], SECRET)
    token = AuthToken.issue(AuthorityLevel.SYSTEM, "demo-agent", ttl_seconds=60, secret=SECRET)

    agent = Agent(mock_model)
    cathedral = LoggingCathedral(
        validator,
        agent,
        retry=RetryConfig(max_attempts=3, base_delay=0.05),
    )

    print()
    print(f"  Initial state : {state.values}")
    print()

    event = await cathedral.step("update the score", token)

    print()
    print(f"  Final state   : {state.values}")
    print()
    print("=" * 52)
    print(f"  Result: {'OK' if event.success else 'FAILED'}")
    print("=" * 52)
    print()


if __name__ == "__main__":
    asyncio.run(main())
