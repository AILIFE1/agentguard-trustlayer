"""Core data types: State, Action, Update."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from trustlayer.auth import AuthToken


@dataclass
class State:
    """Mutable key-value store with per-key lock support."""

    values: Dict[str, Any]
    locks: Dict[str, bool] = field(default_factory=dict)


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
