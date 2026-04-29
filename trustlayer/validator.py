"""Validator: applies updates against constraints with full audit trail."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

from trustlayer.constraints import Constraint
from trustlayer.types import Action, State, Update

logger = logging.getLogger("trustlayer.validator")


class Verifier:
    """Hook called for external_call actions. Override to add real checks."""

    def verify(self, action: Action) -> bool:
        return True


@dataclass
class ValidationEvent:
    """Immutable record of a single validation attempt."""

    success: bool
    description: str
    failed_constraints: List[str] = field(default_factory=list)
    failed_constraint: Optional[str] = None   # backward compat: first of failed_constraints
    action: str = ""
    timestamp: float = field(default_factory=time.time)
    audit_hash: str = ""
    prev_hash: str = ""

    def __str__(self) -> str:
        if self.success:
            return f"[OK] {self.description}"
        return f"[FAIL] {self.description} | constraints: {self.failed_constraints}"


class Validator:
    """Deterministic state validator with tamper-evident audit chain.

    Applies Updates atomically: if any constraint fails the state is
    rolled back and a ValidationEvent records the failure. Every event
    is chained via SHA-256 so the full history can be verified offline.
    """

    def __init__(
        self,
        state: State,
        constraints: List[Constraint],
        secret: bytes,
        verifier: Optional[Verifier] = None,
    ):
        self.state = state
        self.constraints = sorted(constraints, key=lambda c: c.priority)
        self.secret = secret
        self.verifier = verifier or Verifier()
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

    def _all_violations(self, snapshot: Optional[dict] = None) -> List[str]:
        return [c.name for c in self.constraints if not c.check(self.state.values, snapshot)]

    def _make_event(
        self,
        success: bool,
        description: str,
        failed: List[str],
        action: str = "",
    ) -> ValidationEvent:
        h = self._compute_hash(description, success)
        event = ValidationEvent(
            success=success,
            description=description,
            failed_constraints=failed,
            failed_constraint=failed[0] if failed else None,
            action=action,
            timestamp=time.time(),
            audit_hash=h,
            prev_hash=self._last_hash,
        )
        self._last_hash = h
        logger.info(str(event))
        return event

    def apply_update(self, update: Update) -> ValidationEvent:
        """Apply *update* and return a structured ValidationEvent."""
        return self.validate_update(update)

    def validate_update(self, update: Update) -> ValidationEvent:
        """Validate and apply *update*, returning a full ValidationEvent."""
        if not update.token.verify(self.secret):
            return self._make_event(False, update.description, ["invalid or expired token"])

        snapshot = self.state.values.copy()
        policy = update.policy

        # pessimistic: work on a copy, only commit if constraints pass
        # optimistic: work directly on state, rollback if constraints fail
        target = snapshot.copy() if policy == "pessimistic" else self.state.values

        for action in update.actions:
            if self.state.is_locked(action.target):
                if policy == "optimistic":
                    self.state.values = snapshot
                return self._make_event(
                    False, update.description, [f"key '{action.target}' is locked"], action.type
                )

            if action.type in ("update", "set"):
                target[action.target] = action.value
            elif action.type == "increment":
                target[action.target] = target.get(action.target, 0) + action.value
            elif action.type == "external_call":
                if not self.verifier.verify(action):
                    if policy == "optimistic":
                        self.state.values = snapshot
                    return self._make_event(
                        False, update.description, ["verifier rejected external_call"], action.type
                    )
                target[action.target] = action.value
            else:
                if policy == "optimistic":
                    self.state.values = snapshot
                return self._make_event(
                    False, update.description, [f"unknown action type '{action.type}'"], action.type
                )

        if policy == "pessimistic":
            self.state.values = target

        failed = self._all_violations(snapshot)
        if failed:
            self.state.values = snapshot
            return self._make_event(False, update.description, failed)

        return self._make_event(True, update.description, [])
