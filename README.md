# TrustLayer

**A deterministic validation layer for AI and autonomous systems.**

---

## The Problem

AI agents make decisions — but decisions are not always safe to execute.

Without a validation layer, an agent can:
- Write invalid state
- Bypass access controls
- Make irreversible changes without authorisation

TrustLayer solves this by **separating decision-making (AI) from execution (validated system).**

The agent proposes. TrustLayer decides whether to allow it.

---

## How It Works

```
AI Agent  -->  Proposal  -->  TrustLayer  -->  Execution
                                  ^
                             Constraints
                          (rules you define)
```

Every update goes through:

1. **Auth check** — is the token valid and in-date?
2. **Lock check** — is the target key frozen?
3. **Constraint check** — does the new state pass all rules?
4. **Rollback** — if any check fails, state is restored automatically

---

## Features

- **Constraint-based validation** — define rules as Python callables
- **Composable logic** — combine constraints with `&`, `|`, `~`
- **Authenticated authority** — HMAC-signed tokens with TTL expiry
- **Safe state updates** — atomic rollback on any failure
- **Async agent loop** — built-in retry with exponential backoff
- **Audit trail** — every validation returns a `ValidationEvent` with the failure reason
- **Zero dependencies** — standard library only

---

## Quick Start

```bash
python examples/demo.py
```

### Example output

```
[REJECTED] set score to 9999     | constraint: score_in_range
[RETRYING] attempt 2 of 3...
[ACCEPTED] set a valid score     | score: 50 -> 42
```

---

## Code Example

```python
import asyncio
import json
from trustlayer import (
    Agent, AuthorityLevel, AuthToken, Cathedral,
    LambdaConstraint, RetryConfig, State, Validator,
)

SECRET = b"my-secret"

# Define constraints
score_ok = LambdaConstraint("score_ok", lambda v: 0 <= v.get("score", 0) <= 100)

# Set up state and validator
state = State(values={"score": 50})
validator = Validator(state, [score_ok], SECRET)

# Issue an authority token
token = AuthToken.issue(AuthorityLevel.SYSTEM, "my-agent", ttl_seconds=60, secret=SECRET)

# Wire up an async model
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

## Project Structure

```
trustlayer/
├── trustlayer/
│   ├── __init__.py       # Public API + logging setup
│   ├── auth.py           # AuthToken, AuthorityLevel
│   ├── constraints.py    # Constraint, LambdaConstraint, And/Or/Not
│   ├── types.py          # State, Action, Update
│   ├── validator.py      # Validator, ValidationEvent
│   └── engine.py         # Agent, Cathedral, RetryConfig
└── examples/
    └── demo.py           # Runnable walkthrough
```

---

## License

MIT
