"""Composable constraint primitives for state validation."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional


class Constraint:
    """Base class for all state constraints."""

    def __init__(
        self,
        name: str,
        priority: int = 100,
        *,
        block: str = "",
        author: str = "",
        reason: str = "",
    ):
        self.name = name
        self.priority = priority
        self.block = block    # logical group, e.g. "identity", "resource", "scope"
        self.author = author  # who defined this constraint
        self.reason = reason  # why this constraint exists

    def check(self, values: Dict[str, Any], original: Optional[Dict[str, Any]] = None) -> bool:
        raise NotImplementedError

    def __and__(self, other: "Constraint") -> "Constraint":
        return AndConstraint(self, other)

    def __or__(self, other: "Constraint") -> "Constraint":
        return OrConstraint(self, other)

    def __invert__(self) -> "Constraint":
        return NotConstraint(self)


class LambdaConstraint(Constraint):
    """Constraint backed by an arbitrary callable.

    Accepts both single-arg ``fn(values)`` and two-arg ``fn(values, original)``
    callables — arity is detected at construction time.
    """

    def __init__(
        self,
        name: str,
        fn: Callable,
        priority: int = 100,
        *,
        block: str = "",
        author: str = "",
        reason: str = "",
    ):
        super().__init__(name, priority, block=block, author=author, reason=reason)
        self.fn = fn
        try:
            self._two_arg = len(inspect.signature(fn).parameters) >= 2
        except (ValueError, TypeError):
            self._two_arg = False

    def check(self, values: Dict[str, Any], original: Optional[Dict[str, Any]] = None) -> bool:
        if self._two_arg:
            return self.fn(values, original)
        return self.fn(values)


class AndConstraint(Constraint):
    def __init__(self, a: Constraint, b: Constraint):
        super().__init__(f"{a.name} AND {b.name}", min(a.priority, b.priority))
        self.a, self.b = a, b

    def check(self, values: Dict[str, Any], original: Optional[Dict[str, Any]] = None) -> bool:
        return self.a.check(values, original) and self.b.check(values, original)


class OrConstraint(Constraint):
    def __init__(self, a: Constraint, b: Constraint):
        super().__init__(f"{a.name} OR {b.name}", min(a.priority, b.priority))
        self.a, self.b = a, b

    def check(self, values: Dict[str, Any], original: Optional[Dict[str, Any]] = None) -> bool:
        return self.a.check(values, original) or self.b.check(values, original)


class NotConstraint(Constraint):
    def __init__(self, inner: Constraint):
        super().__init__(f"NOT {inner.name}", inner.priority)
        self.inner = inner

    def check(self, values: Dict[str, Any], original: Optional[Dict[str, Any]] = None) -> bool:
        return not self.inner.check(values, original)
