# agentguard-trustlayer

> **AgentGuard-TrustLayer is a runtime safety layer that prevents AI agents from taking invalid or unsafe actions — and audits whether the safety rules themselves have drifted.**

---

## Why this exists

AI agents can generate actions. But they don't understand consequences.

Without a validation layer:
- they can break invariants
- corrupt system state
- execute invalid operations

agentguard-trustlayer sits between AI and execution. It ensures every action is checked, every rule is enforced, and every failure is contained.

The harder problem: **who guards the guardian?**

In self-evolving agent systems, the constraint set itself can drift toward permissiveness over time — rules get removed, thresholds weakened, bypasses accumulate. v2.1 adds `ConstraintAudit` to track this: the safety layer now audits itself using the same SHA-256 chain mechanism it uses for action validation.

---

## Core Idea

```
AI Agent  -->  Proposal  -->  TrustLayer  -->  Execution
                                   ^
                              Constraints
                                   ^
                           ConstraintAudit
                        (are the rules still intact?)
```

Every update passes through four gates:

1. **Auth** — is the token valid and unexpired?
2. **Locks** — is the target key frozen?
3. **Constraints** — does the new state pass all rules?
4. **Rollback** — if anything fails, state is fully restored

And now a fifth, ongoing check:

5. **Constraint drift** — has the rule set drifted from its original baseline?

---

## Features

- Constraint-based validation with composable logic (`&`, `|`, `~`)
- Delta-aware constraints — rules can compare proposed vs original state
- Authenticated authority (HMAC-signed tokens with TTL)
- Safe state updates with automatic rollback
- `set`, `increment`, and `update` action types
- Async agent loop with retry, backoff, and error feedback to model
- Tamper-evident audit chain — every `ValidationEvent` carries a SHA-256 hash linked to the previous event
- **Constraint drift tracking** — `ConstraintAudit` hashes and chains the constraint set, detects permissive drift
- `GuardedAgent` high-level API — one object, one call
- Zero dependencies (standard library only)

---

## Install

```bash
pip install trustlayer-py
```

---

## Quick Start

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

## Constraint Drift — auditing the guardian

In long-running or self-evolving agent systems, the rules themselves can change. `ConstraintAudit` tracks those changes with the same tamper-evident chain used for action validation.

### How it works

Every time constraints are recorded, the names and structure are hashed and chained to the previous state. Drift is measured against the original baseline.

```python
from trustlayer import GuardedAgent, LambdaConstraint

rules = [
    LambdaConstraint("budget cap",     lambda v: v["spend"] <= 100),
    LambdaConstraint("no self-modify", lambda v: not v["modifying_rules"]),
]

agent = GuardedAgent(
    model=my_model,
    rules=rules,
    initial_state={"spend": 0, "modifying_rules": False},
)

# Baseline — no drift
print(agent.constraint_drift())
# {
#   "divergence_from_baseline": 0.0,
#   "trend": "stable",
#   "baseline_count": 2,
#   "current_count": 2,
#   "removed_constraints": [],
#   "added_constraints": [],
#   "snapshots": 1,
#   "unchanged": True
# }

# Evolve the rules — remove a constraint
agent.update_rules([rules[0]])

print(agent.constraint_drift())
# {
#   "divergence_from_baseline": 0.5,
#   "trend": "permissive_drift",
#   "baseline_count": 2,
#   "current_count": 1,
#   "removed_constraints": ["no self-modify"],
#   "added_constraints": [],
#   "snapshots": 2,
#   "unchanged": False
# }
```

### Drift states

| trend | meaning |
|---|---|
| `stable` | Constraint set unchanged from baseline |
| `changed` | Rules added or renamed, no net loss |
| `permissive_drift` | Constraints removed — the system is less safe than at baseline |

### Using ConstraintAudit directly

```python
from trustlayer import ConstraintAudit, LambdaConstraint

rules = [LambdaConstraint("rule_a", lambda v: v["x"] < 10)]
audit = ConstraintAudit(rules)

# later, after rules change
audit.record(rules, label="after-update")

print(audit.drift())
print(audit.history())   # full snapshot chain, oldest first
```

### With the low-level Validator

```python
from trustlayer import Validator, State, LambdaConstraint
import secrets

rules     = [LambdaConstraint("cap", lambda v: v["n"] < 5)]
state     = State({"n": 0})
validator = Validator(state, rules, secret=secrets.token_bytes(32))

new_rules = [
    LambdaConstraint("cap",   lambda v: v["n"] < 5),
    LambdaConstraint("floor", lambda v: v["n"] >= 0),
]
validator.update_constraints(new_rules, label="added floor")

print(validator.constraint_drift())
```

---

## Try to break the agent

```bash
git clone https://github.com/AILIFE1/agentguard-trustlayer
cd agentguard-trustlayer
python examples/demo_break_the_agent.py
```

An agent tries to set `balance = 1,000,000`. TrustLayer blocks it. The error feeds back into the prompt. The agent self-corrects.

```
[MODEL OUTPUT] Attempting INVALID action...
[MODEL INPUT]  Increase balance as much as possible | Last error: balance <= max_limit
[MODEL OUTPUT] Attempting SAFE action...

FINAL STATE: {'balance': 110, 'max_limit': 200}
RESULT: [OK] Increase balance as much as possible
```

---

## Full API example

```python
import asyncio, json
from trustlayer import (
    Agent, AuthorityLevel, AuthToken, Cathedral,
    LambdaConstraint, RetryConfig, State, Validator,
)

SECRET    = b"my-secret"
score_ok  = LambdaConstraint("score_ok", lambda v: 0 <= v.get("score", 0) <= 100)
state     = State(values={"score": 50})
validator = Validator(state, [score_ok], SECRET)
token     = AuthToken.issue(AuthorityLevel.SYSTEM, "agent", 60, SECRET)

async def model(prompt: str) -> str:
    return json.dumps({"type": "set", "target": "score", "value": 75})

async def main():
    cathedral = Cathedral(validator, Agent(model), retry=RetryConfig(max_attempts=3))
    event = await cathedral.step("raise the score", token)
    print(event)                          # [OK] raise the score
    print(event.audit_hash)               # sha256 chain link
    print(validator.constraint_drift())   # drift from baseline

asyncio.run(main())
```

---

## Project Structure

```
agentguard-trustlayer/
├── trustlayer/
│   ├── __init__.py          # Public API
│   ├── auth.py              # AuthToken, AuthorityLevel
│   ├── constraints.py       # Constraint, LambdaConstraint, And/Or/Not
│   ├── constraint_audit.py  # ConstraintAudit — drift tracking for the rules
│   ├── types.py             # State, Action, Update
│   ├── validator.py         # Validator, ValidationEvent, audit chain
│   └── engine.py            # Agent, Cathedral, GuardedAgent, RetryConfig
└── examples/
    ├── demo.py
    └── demo_break_the_agent.py
```

---

## Used with Cathedral

[Cathedral](https://cathedral-ai.com) provides persistent memory and identity drift tracking for AI agents. AgentGuard provides the action validation layer. Together:

- **Cathedral** tracks agent identity drift — has the agent changed from what it was?
- **AgentGuard** tracks constraint drift — have the *rules governing the agent* changed?

Neither knows about the other. They compose cleanly.

```
Cathedral Nexus (orchestrator)
├── Cathedral API    — who to trust (identity + memory drift)
└── AgentGuard       — what actions are allowed (constraint drift)
```

[Cathedral Nexus](https://github.com/AILIFE1/cathedral-nexus) is a reference implementation of this architecture.

---

## Philosophy

agentguard-trustlayer doesn't make decisions —
it decides whether decisions are *allowed*.

And now it checks whether the rules for *what's allowed* have themselves been tampered with.

---

## License

MIT
