"""Validator: applies updates against constraints with full audit trail."""

from __future__ import annotations

import logging
from dataclasses import dataclass
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

    def __str__(self) -> str:
        if self.success:
            return f"[OK] {self.description}"
        return f"[FAIL] {self.description} | constraint: {self.failed_constraint}"


class Validator:
    """Deterministic state validator.

    Applies Updates atomically: if any constraint fails the state is
    rolled back and a ValidationEvent records the failure.
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

    def _first_violation(self) -> Optional[str]:
        for c in self.constraints:
            if not c.check(self.state.values):
                return c.name
        return None

    def apply_update(self, update: Update) -> bool:
        """Apply *update* and return True on success.

        Rolls back state automatically on constraint violation or
        auth failure.
        """
        event = self.validate_update(update)
        logger.info(str(event))
        return event.success

    def validate_update(self, update: Update) -> ValidationEvent:
        """Like apply_update but returns a full ValidationEvent."""
        if not update.token.verify(self.secret):
            return ValidationEvent(
                success=False,
                description=update.description,
                failed_constraint="invalid or expired token",
            )

        snapshot = self.state.values.copy()

        for action in update.actions:
            if self.state.locks.get(action.target, False):
                self.state.values = snapshot
                return ValidationEvent(
                    success=False,
                    description=update.description,
                    failed_constraint=f"key '{action.target}' is locked",
                )
            if action.type == "update":
                self.state.values[action.target] = action.value

        failed = self._first_violation()
        if failed:
            self.state.values = snapshot
            return ValidationEvent(
                success=False,
                description=update.description,
                failed_constraint=failed,
            )

        return ValidationEvent(success=True, description=update.description)
