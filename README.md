# TrustLayer

**Deterministic validation engine for AI and autonomous systems.**

TrustLayer wraps any async AI agent in a constraint layer that enforces rules
on every state update — with signed authority tokens, atomic rollback, and
exponential-backoff retry built in.

---

## Key Features

- **Composable constraints** — combine rules with `&`, `|`, `~` operators
- **Atomic rollback** — state is never partially updated on failure
- **Signed tokens** — HMAC-SHA256 authority tokens with TTL expiry
- **Retry strategies** — configurable backoff for transient failures
- **Zero dependencies** — standard library only

---

## Quick Start

```python
import asyncio
import json
from trustlayer import (
    Agent, AuthorityLevel, AuthToken, Cathedral,
    LambdaConstraint, RetryConfig, State, Validator,
)

SECRET = b"my-secret"

score_ok = LambdaConstraint("score_ok", lambda v: 0 <= v.get("score", 0) <= 100)

state = State(values={"score": 50})
validator = Validator(state, [score_ok], SECRET)
token = AuthToken.issue(AuthorityLevel.SYSTEM, "my-agent", ttl_seconds=60, secret=SECRET)

async def my_model(prompt: str) -> str:
    return json.dumps({"type": "update", "target": "score", "value": 75})

async def main():
    cathedral = Cathedral(validator, Agent(my_model), retry=RetryConfig(max_attempts=3))
    event = await cathedral.step("raise the score", token)
    print(event)          # [OK] raise the score
    print(state.values)   # {'score': 75}

asyncio.run(main())
```

---

## Running the Demo

```bash
python examples/demo.py
```

The demo exercises four scenarios:
1. Direct update that violates a constraint (rejected, state rolled back)
2. Agent that proposes a bad value then a valid one (retry succeeds on attempt 2)
3. Attempt to modify a locked key (blocked)
4. Expired token (rejected before any state change)

---

## Project Structure

```
trustlayer/
├── trustlayer/
│   ├── __init__.py      # Public API + logging setup
│   ├── auth.py          # AuthToken, AuthorityLevel
│   ├── constraints.py   # Constraint, LambdaConstraint, And/Or/Not
│   ├── types.py         # State, Action, Update
│   ├── validator.py     # Validator, ValidationEvent
│   └── engine.py        # Agent, Cathedral, RetryConfig
└── examples/
    └── demo.py
```

---

## License

MIT
