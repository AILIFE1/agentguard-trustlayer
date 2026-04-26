# TrustLayer

Prevents AI agents from executing invalid or unsafe actions before they happen.

---

## Why this exists

AI agents can generate actions.

But they don't understand consequences.

Without a validation layer:
- they can break invariants
- corrupt system state
- execute invalid operations

TrustLayer sits between AI and execution.

It ensures:
- every action is checked
- every rule is enforced
- every failure is contained

---

## Core Idea

TrustLayer separates:

**decision-making (AI)**
from
**execution (validated system)**

---

## How it works

```
AI Agent  -->  Proposal  -->  TrustLayer  -->  Execution
                                   ^
                              Constraints
```

Every update passes through four gates:

1. **Auth** — is the token valid and unexpired?
2. **Locks** — is the target key frozen?
3. **Constraints** — does the new state pass all rules?
4. **Rollback** — if anything fails, state is fully restored

---

## Example: Preventing Bad AI Actions

An AI agent attempts:

```
C = 100
```

But the system enforces:

```
C = B + 5
```

TrustLayer rejects the action before it can corrupt the system.

The agent retries with a valid update, and the system remains stable.

---

## Features

- Constraint-based validation
- Authenticated authority (HMAC-signed tokens with TTL)
- Safe state updates with automatic rollback
- Composable logic (`&`, `|`, `~` operators)
- Async agent loop with retry and backoff
- Full audit trail via `ValidationEvent`
- Zero dependencies (standard library only)

---

## Practical Use Cases

- Prevent AI agents from breaking business rules
- Enforce invariants in automated systems
- Add safety layer to LLM workflows
- Control multi-agent environments with authority

---

## Quick Start

```bash
python examples/demo.py
```

---

## Example Output

```
--- Agent Attempt 1 ---
Goal: Force C = 100
REJECTED: Would break constraint (C must equal B + 5)
System prevented invalid state.

--- Agent Attempt 2 ---
Adjusting strategy...
ACCEPTED: State remains consistent
Final State: {'A': 10, 'B': 20, 'C': 25}
```

---

## Code Example

```python
import asyncio, json
from trustlayer import (
    Agent, AuthorityLevel, AuthToken, Cathedral,
    LambdaConstraint, RetryConfig, State, Validator,
)

SECRET = b"my-secret"

score_ok = LambdaConstraint("score_ok", lambda v: 0 <= v.get("score", 0) <= 100)

state     = State(values={"score": 50})
validator = Validator(state, [score_ok], SECRET)
token     = AuthToken.issue(AuthorityLevel.SYSTEM, "agent", ttl_seconds=60, secret=SECRET)

async def model(prompt: str) -> str:
    return json.dumps({"type": "update", "target": "score", "value": 75})

async def main():
    cathedral = Cathedral(validator, Agent(model), retry=RetryConfig(max_attempts=3))
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

## Philosophy

TrustLayer doesn't make decisions —
it decides whether decisions are *allowed*.

---

## License

MIT
