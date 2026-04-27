"""Validator: applies updates against constraints with full audit trail."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

from trustlayer.constraints import Constraint
from trustlayer.types import State, Update

logger = logging.getLogger("trustlayer.validator")


@dataclass
class ValidationEvent:
    """Immutable record of a single validation attempt."""

    success: bool
    description: str
    failed_constraint: Optional[str] = None
    audit_hash: str = ""
    prev_hash: str = ""
    ts: float = field(default_factory=time.time)

    def __str__(self) -> str:
        if self.success:
            return f"[OK] {self.description}"
        return f"[FAIL] {self.description} | constraint: {self.failed_constraint}"


class Validator:
    """Deterministic state validator with tamper-evident audit chain.

    Applies Updates atomically: if any constraint fails the state is
    rolled back and a ValidationEvent records the failure.  Every event
    is chained via SHA-256 so the full history can be verified offline.
    """

    def __init__(
        self,
        state: State,
        constraints: List[Constraint],
        secret: bytes,
    ):
        self.state = state
        # Lower priority value = checked first
        self.constraints = sorted(constraints, key=lambda c: c.priority)
        self.secret = secret
        self._last_hash = "GENESIS"

    def _compute_hash(self, description: str, success: bool) -> str:
        payload = json.dumps(
            {
                "desc": description,
                "state": self.state.values,
                "prev": self._last_hash,
                "success": success,
                "ts": time.time(),
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def _first_violation(self, snapshot: Optional[dict] = None) -> Optional[str]:
        for c in self.constraints:
            if not c.check(self.state.values, snapshot):
                return c.name
        return None

    def _make_event(self, success: bool, description: str, failed: Optional[str]) -> ValidationEvent:
        h = self._compute_hash(description, success)
        event = ValidationEvent(
            success=success,
            description=description,
            failed_constraint=failed,
            audit_hash=h,
            prev_hash=self._last_hash,
            ts=time.time(),
        )
        self._last_hash = h
        logger.info(str(event))
        return event

    def apply_update(self, update: Update) -> bool:
        """Apply *update* and return True on success."""
        return self.validate_update(update).success

    def validate_update(self, update: Update) -> ValidationEvent:
        """Like apply_update but returns a full ValidationEvent."""
        if not update.token.verify(self.secret):
            return self._make_event(False, update.description, "invalid or expired token")

        snapshot = self.state.values.copy()

        for action in update.actions:
            if self.state.is_locked(action.target):
                self.state.values = snapshot
                return self._make_event(
                    False, update.description, f"key '{action.target}' is locked"
                )

            if action.type in ("update", "set"):
                self.state.values[action.target] = action.value
            elif action.type == "increment":
                self.state.values[action.target] = (
                    self.state.values.get(action.target, 0) + action.value
                )
            else:
                self.state.values = snapshot
                return self._make_event(
                    False, update.description, f"unknown action type '{action.type}'"
                )

        failed = self._first_violation(snapshot)
        if failed:
            self.state.values = snapshot

        return self._make_event(failed is None, update.description, failed)
