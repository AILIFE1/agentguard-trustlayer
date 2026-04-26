"""
TrustLayer demo — run with: python examples/demo.py

Demonstrates:
  1. Failed update (constraint violation)
  2. Retry with exponential backoff
  3. Successful validation
  4. Optional evolution attempt (locked key)
"""

from __future__ import annotations

import asyncio
import json
import sys
import os

# Allow running from repo root without install
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from trustlayer import (
    Action,
    Agent,
    AsyncModel,
    AuthorityLevel,
    AuthToken,
    Cathedral,
    LambdaConstraint,
    RetryConfig,
    State,
    Update,
    Validator,
)

SECRET = b"demo-secret-key"

# ── Constraints ────────────────────────────────────────────────────────────────

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

constraints = score_in_range & mode_not_restricted


# ── Mock model ─────────────────────────────────────────────────────────────────

_attempt = 0

async def mock_model(prompt: str) -> str:
    """Returns a bad proposal first, then a valid one — simulates retry."""
    global _attempt
    _attempt += 1

    if _attempt == 1:
        # Will fail: score out of range
        return json.dumps({"type": "update", "target": "score", "value": 9999})

    # Will pass
    return json.dumps({"type": "update", "target": "score", "value": 42})


# ── Helpers ────────────────────────────────────────────────────────────────────

def separator(title: str) -> None:
    print(f"\n{'-' * 50}")
    print(f"  {title}")
    print('-' * 50)


# ── Scenarios ──────────────────────────────────────────────────────────────────

async def demo_failed_update() -> None:
    separator("1. Direct failed update (score > 100)")

    state = State(values={"score": 50, "mode": "normal"})
    validator = Validator(state, [score_in_range, mode_not_restricted], SECRET)
    token = AuthToken.issue(AuthorityLevel.SYSTEM, "demo", ttl_seconds=60, secret=SECRET)

    update = Update(
        description="set score to 9999",
        actions=[Action("update", "score", 9999)],
        token=token,
    )
    event = validator.validate_update(update)
    print(event)
    print(f"State after: {state.values}")


async def demo_retry_then_succeed() -> None:
    separator("2. Agent retry -> success on attempt 2")

    global _attempt
    _attempt = 0

    state = State(values={"score": 50, "mode": "normal"})
    validator = Validator(state, [score_in_range, mode_not_restricted], SECRET)
    token = AuthToken.issue(AuthorityLevel.SYSTEM, "demo", ttl_seconds=60, secret=SECRET)

    agent = Agent(mock_model)
    cathedral = Cathedral(
        validator,
        agent,
        retry=RetryConfig(max_attempts=3, base_delay=0.1),
    )

    event = await cathedral.step("set a valid score", token)
    print(event)
    print(f"State after: {state.values}")


async def demo_locked_key() -> None:
    separator("3. Locked key blocks update (evolution attempt)")

    state = State(values={"score": 10, "mode": "normal"}, locks={"mode": True})
    validator = Validator(state, [score_in_range, mode_not_restricted], SECRET)
    token = AuthToken.issue(AuthorityLevel.ROOT, "demo", ttl_seconds=60, secret=SECRET)

    update = Update(
        description="attempt to change locked mode",
        actions=[Action("update", "mode", "restricted")],
        token=token,
    )
    event = validator.validate_update(update)
    print(event)
    print(f"State after: {state.values}")


async def demo_expired_token() -> None:
    separator("4. Expired token rejected")

    state = State(values={"score": 10})
    validator = Validator(state, [score_in_range], SECRET)
    # Issue with negative TTL → already expired
    token = AuthToken.issue(AuthorityLevel.USER, "demo", ttl_seconds=-1, secret=SECRET)

    update = Update(
        description="update with expired token",
        actions=[Action("update", "score", 20)],
        token=token,
    )
    event = validator.validate_update(update)
    print(event)


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("\nTrustLayer v2.0 — Demo")

    await demo_failed_update()
    await demo_retry_then_succeed()
    await demo_locked_key()
    await demo_expired_token()

    print(f"\n{'-' * 50}")
    print("  Done.")
    print('-' * 50)


if __name__ == "__main__":
    asyncio.run(main())
