"""
TrustLayer demo  --  python examples/demo.py

Story:
  An agent manages a small system with three values: A, B, and C.
  One hard rule exists: C must always equal B + 5.

  The agent first tries to set C = 100 (breaks the rule).
  TrustLayer rejects it and rolls back state.
  The agent retries with C = 25 (correct).
  TrustLayer accepts it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Ensure emoji render correctly on all terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import logging
logging.basicConfig(level=logging.INFO)
logging.disable(logging.CRITICAL)   # silence internal logs for clean demo output

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
    ValidationEvent,
    Validator,
)
from trustlayer.engine import parse_action

SECRET = b"demo-secret"

# ---------------------------------------------------------------------------
# Constraint:  C must equal B + 5
# ---------------------------------------------------------------------------

c_equals_b_plus_5 = LambdaConstraint(
    "C must equal B + 5",
    lambda v: v.get("C", 0) == v.get("B", 0) + 5,
)

# ---------------------------------------------------------------------------
# Mock model  (bad proposal first, valid proposal second)
# ---------------------------------------------------------------------------

_call = 0


async def mock_model(prompt: str) -> str:
    global _call
    _call += 1
    if _call == 1:
        return json.dumps({"type": "update", "target": "C", "value": 100})
    return json.dumps({"type": "update", "target": "C", "value": 25})


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

W = 50

def header(text: str) -> None:
    print()
    print("=" * W)
    print(f"  {text}")
    print("=" * W)

def show_state(state: State) -> None:
    parts = "  ".join(f"{k}={v}" for k, v in sorted(state.values.items()))
    print(f"\n  [ State ]  {parts}\n")

def rule(text: str = "") -> None:
    if text:
        print(f"  {'-' * (W - 2)}")
        print(f"  {text}")
    else:
        print(f"  {'-' * (W - 2)}")

# ---------------------------------------------------------------------------
# Instrumented Cathedral that prints the story as it runs
# ---------------------------------------------------------------------------

class StorytellerCathedral(Cathedral):

    async def step(self, goal: str, token: AuthToken) -> ValidationEvent:
        delay = self.retry.base_delay
        last_event: ValidationEvent | None = None

        for attempt in range(1, self.retry.max_attempts + 1):
            proposal = await self.agent.propose(goal)
            action = parse_action(proposal)

            print(f"\n--- Agent Attempt {attempt} ---")

            if not action:
                print("Goal: (unparseable proposal)")
                last_event = ValidationEvent(
                    success=False,
                    description=goal,
                    failed_constraint="unparseable proposal",
                )
                print("REJECTED: Could not parse agent output")
                print("System prevented invalid state.")
            else:
                print(f"Goal: Force {action.target} = {action.value}")

                update = Update(description=goal, actions=[action], token=token)
                last_event = self.validator.validate_update(update)

                if last_event.success:
                    print("✅ ACCEPTED: State remains consistent")
                    print(f"Final State: {self.validator.state.values}")
                    return last_event
                else:
                    print(f"❌ REJECTED: Would break constraint ({last_event.failed_constraint})")
                    print("System prevented invalid state.")

            if attempt < self.retry.max_attempts:
                print("\nAdjusting strategy...")
                await asyncio.sleep(delay)
                delay *= self.retry.backoff_factor

        return last_event  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    global _call
    _call = 0

    state = State(values={"A": 10, "B": 20, "C": 10})
    validator = Validator(state, [c_equals_b_plus_5], SECRET)
    token = AuthToken.issue(AuthorityLevel.SYSTEM, "demo-agent", ttl_seconds=60, secret=SECRET)

    agent = Agent(mock_model)
    cathedral = StorytellerCathedral(
        validator,
        agent,
        retry=RetryConfig(max_attempts=3, base_delay=0.05),
    )

    header("TrustLayer v2.0  --  Validation Demo")

    print()
    print("  Rule:   C must always equal B + 5")
    print("  Agent:  will first break the rule, then fix it")

    show_state(state)

    event = await cathedral.step("update C", token)

    print()
    status = "PASSED" if event.success else "FAILED"
    print(f"\n[ Result: {status} ]")
    print("=" * W)
    print()


if __name__ == "__main__":
    asyncio.run(main())
