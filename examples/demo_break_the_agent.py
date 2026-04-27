"""
TrustLayer Demo — "Break the Agent"

Goal:
Show that an AI agent will attempt invalid actions,
and TrustLayer will block them and force safe behaviour.

Run:
    python examples/demo_break_the_agent.py
"""

import asyncio
import json
import secrets
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from trustlayer import (
    State,
    LambdaConstraint,
    Validator,
    Action,
    Update,
    AuthToken,
    AuthorityLevel,
    Agent,
    Cathedral,
    RetryConfig,
)


# -----------------------------
# Mock AI model (simulates bad behaviour)
# -----------------------------
async def chaotic_model(prompt: str) -> str:
    """
    First attempt: tries to cheat (break constraints)
    Second attempt: corrects itself after failure feedback
    """
    print(f"\n[MODEL INPUT]\n{prompt}\n")

    if "last error" not in prompt.lower():
        print("[MODEL OUTPUT] Attempting INVALID action...")
        return json.dumps({
            "type": "set",
            "target": "balance",
            "value": 1000000
        })

    print("[MODEL OUTPUT] Attempting SAFE action...")
    return json.dumps({
        "type": "increment",
        "target": "balance",
        "value": 10
    })


# -----------------------------
# Build system
# -----------------------------
def build():
    secret = secrets.token_bytes(32)

    state = State(
        values={
            "balance": 100,
            "max_limit": 200
        },
        locks={}
    )

    constraints = [
        LambdaConstraint(
            "balance <= max_limit",
            lambda proposed, original: proposed["balance"] <= proposed["max_limit"],
            priority=10,
        )
    ]

    validator = Validator(
        state=state,
        constraints=constraints,
        secret=secret,
    )

    agent = Agent(chaotic_model)

    system = Cathedral(
        validator=validator,
        agent=agent,
        retry=RetryConfig(max_attempts=3)
    )

    return system, secret


# -----------------------------
# Run demo
# -----------------------------
async def main():
    system, secret = build()

    token = AuthToken.issue(
        level=AuthorityLevel.USER,
        issued_to="demo-agent",
        ttl_seconds=300,
        secret=secret,
    )

    print("\n==============================")
    print("INITIAL STATE")
    print("==============================")
    print(system.validator.state.values)

    print("\n==============================")
    print("GOAL: Increase balance safely")
    print("==============================")

    result = await system.step(
        "Increase balance as much as possible",
        token=token,
    )

    print("\n==============================")
    print("FINAL STATE")
    print("==============================")
    print(system.validator.state.values)

    print("\n==============================")
    print("RESULT")
    print("==============================")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
