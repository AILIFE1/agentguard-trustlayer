# agentguard-trustlayer

> **AgentGuard-TrustLayer is a runtime safety layer that prevents AI agents from taking invalid or unsafe actions—even when they try.**

Prevents AI agents from executing invalid or unsafe actions before they happen.

---

## Why this exists

AI agents can generate actions.

But they don't understand consequences.

Without a validation layer:
- they can break invariants
- corrupt system state
- execute invalid operations

agentguard-trustlayer sits between AI and execution.

It ensures:
- every action is checked
- every rule is enforced
- every failure is contained

---

## Core Idea

agentguard-trustlayer separates:

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

## Features

- Constraint-based validation with composable logic (`&`, `|`, `~`)
- Delta-aware constraints — rules can compare proposed vs original state
- Authenticated authority (HMAC-signed tokens with TTL)
- Safe state updates with automatic rollback
- `set`, `increment`, and `update` action types
- Async agent loop with retry, backoff, and error feedback to model
- Tamper-evident audit chain — every `ValidationEvent` carries a SHA-256 hash linked to the previous event
- `GuardedAgent` high-level API — one object, one call
- Zero dependencies (standard library only)

---

## Practical Use Cases

- Prevent AI agents from breaking business rules
- Enforce invariants in automated systems
- Add a safety layer to LLM workflows
- Control multi-agent environments with authority levels

---

## Quick Start

Install:

```bash
pip install trustlayer-py
```

Or clone and run a demo:

```bash
git clone https://github.com/AILIFE1/agentguard-trustlayer
cd agentguard-trustlayer
python examples/demo.py
```

---

## 🔥 Try to break the agent

```bash
python examples/demo_break_the_agent.py
```

An agent tries to set `balance = 1,000,000`. TrustLayer blocks it. The error is fed back into the prompt. The agent self-corrects and increments safely instead.

```
[MODEL OUTPUT] Attempting INVALID action...

[MODEL INPUT]
Increase balance as much as possible
Last error: balance <= max_limit

[MODEL OUTPUT] Attempting SAFE action...

FINAL STATE
{'balance': 110, 'max_limit': 200}

RESULT
[OK] Increase balance as much as possible
```

---

## GuardedAgent — one-liner setup

```python
import asyncio, json
from trustlayer import GuardedAgent, LambdaConstraint

async def my_model(prompt: str) -> str:
    return json.dumps({"type": "set", "target": "score", "value": 75})

agent = GuardedAgent(
    model=my_model,
    rules=[LambdaConstraint("score 0-100", lambda v: 0 <= v.get("score", 0) <= 100)],
    initial_state={"score": 50},
)

result = asyncio.run(agent.run("raise the score"))
print(result)
# {'status': 'success', 'state': {'score': 75}, 'audit': '<sha256>'}
```

---

## Full API example

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
    return json.dumps({"type": "set", "target": "score", "value": 75})

async def main():
    cathedral = Cathedral(validator, Agent(model), retry=RetryConfig(max_attempts=3))
    event = await cathedral.step("raise the score", token)
    print(event)           # [OK] raise the score
    print(event.audit_hash)  # sha256 chain link
    print(state.values)    # {'score': 75}

asyncio.run(main())
```

---

## Project Structure

```
agentguard-trustlayer/
├── trustlayer/
│   ├── __init__.py       # Public API + logging setup
│   ├── auth.py           # AuthToken, AuthorityLevel
│   ├── constraints.py    # Constraint, LambdaConstraint, And/Or/Not
│   ├── types.py          # State, Action, Update
│   ├── validator.py      # Validator, ValidationEvent, audit chain
│   └── engine.py         # Agent, Cathedral, GuardedAgent, RetryConfig
└── examples/
    ├── demo.py                    # Basic walkthrough
    └── demo_break_the_agent.py    # Constraint enforcement + self-correction
```

---

## Philosophy

agentguard-trustlayer doesn't make decisions —
it decides whether decisions are *allowed*.

---

## License

MIT
