"""Core data types: State, Action, Update, GateDiagnostic, ExternalCallConfig."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from trustlayer.auth import AuthToken


@dataclass
class State:
    """Mutable key-value store with per-key lock support."""

    values: Dict[str, Any]
    locks: Dict[str, bool] = field(default_factory=dict)

    def is_locked(self, key: str) -> bool:
        return self.locks.get(key, False)


@dataclass
class Action:
    """A single atomic operation on a State key."""

    type: str
    target: str
    value: Any = None


@dataclass
class Update:
    """A validated, token-authorized batch of Actions."""

    description: str
    actions: List[Action]
    token: AuthToken
    policy: str = "pessimistic"  # "pessimistic" | "optimistic"


@dataclass
class ExternalCallConfig:
    """Structured payload for external_call actions.

    Use as Action.value when type="external_call" to give verifiers
    structured access to the call parameters::

        action = Action(
            type="external_call",
            target="payment_gateway",
            value=ExternalCallConfig(
                endpoint="https://api.example.com/pay",
                method="POST",
                payload={"amount": 50, "currency": "USD"},
            ),
        )
    """

    endpoint: str
    method: str = "GET"
    payload: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 10


@dataclass
class GateDiagnostic:
    """Explains why a specific constraint blocked an action.

    Attached to ValidationEvent.diagnostics on validation failure so
    callers can surface detailed rejection reasons without re-running
    the constraints manually.
    """

    constraint_name: str
    block: str
    action_type: str
    target_key: str
    current_value: Any
    author: str
    reason: str
