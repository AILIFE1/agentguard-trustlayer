"""Validator: applies updates against constraints with full audit trail."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from trustlayer.constraint_audit import ConstraintAudit
from trustlayer.constraints import Constraint
from trustlayer.types import Action, GateDiagnostic, State, Update

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
    diagnostics: List[GateDiagnostic] = field(default_factory=list)

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
        self.constraint_audit = ConstraintAudit(self.constraints)

    def update_constraints(self, new_constraints: List[Constraint], label: str = "") -> str:
        """Replace the active constraint set and record the change in the audit chain.

        Returns the new constraint hash.
        """
        self.constraints = sorted(new_constraints, key=lambda c: c.priority)
        return self.constraint_audit.record(self.constraints, label=label)

    def constraint_drift(self) -> dict:
        """Return drift metrics for the constraint set since baseline."""
        return self.constraint_audit.drift()

    def _compute_hash(self, description: str, success: bool) -> str:
        import dataclasses

        def _default(obj):
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
            return str(obj)

        payload = json.dumps(
            {
                "desc": description,
                "state": self.state.values,
                "prev": self._last_hash,
                "success": success,
                "ts": time.time(),
            },
            sort_keys=True,
            default=_default,
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def _all_violations(self, snapshot: Optional[dict] = None) -> List[str]:
        return [c.name for c in self.constraints if not c.check(self.state.values, snapshot)]

    def _all_violations_with_diag(
        self,
        snapshot: Optional[dict] = None,
        action: Optional[Action] = None,
    ) -> Tuple[List[str], List[GateDiagnostic]]:
        failed_names: List[str] = []
        diagnostics: List[GateDiagnostic] = []
        for c in self.constraints:
            if not c.check(self.state.values, snapshot):
                failed_names.append(c.name)
                diagnostics.append(GateDiagnostic(
                    constraint_name=c.name,
                    block=getattr(c, "block", ""),
                    action_type=action.type if action else "",
                    target_key=action.target if action else "",
                    current_value=(
                        self.state.values.get(action.target)
                        if action else None
                    ),
                    author=getattr(c, "author", ""),
                    reason=getattr(c, "reason", ""),
                ))
        return failed_names, diagnostics

    def _make_event(
        self,
        success: bool,
        description: str,
        failed: List[str],
        action: str = "",
        diagnostics: Optional[List[GateDiagnostic]] = None,
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
            diagnostics=diagnostics or [],
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

        last_action = update.actions[-1] if update.actions else None
        failed, diagnostics = self._all_violations_with_diag(snapshot, last_action)
        if failed:
            self.state.values = snapshot
            return self._make_event(
                False, update.description, failed,
                last_action.type if last_action else "",
                diagnostics,
            )

        return self._make_event(True, update.description, [])
