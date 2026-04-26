"""Composable constraint primitives for state validation."""

from __future__ import annotations

from typing import Any, Callable, Dict


class Constraint:
    """Base class for all state constraints."""

    def __init__(self, name: str, priority: int = 100):
        self.name = name
        self.priority = priority

    def check(self, values: Dict[str, Any]) -> bool:
        raise NotImplementedError

    def __and__(self, other: "Constraint") -> "Constraint":
        return AndConstraint(self, other)

    def __or__(self, other: "Constraint") -> "Constraint":
        return OrConstraint(self, other)

    def __invert__(self) -> "Constraint":
        return NotConstraint(self)


class LambdaConstraint(Constraint):
    """Constraint backed by an arbitrary callable."""

    def __init__(
        self,
        name: str,
        fn: Callable[[Dict[str, Any]], bool],
        priority: int = 100,
    ):
        super().__init__(name, priority)
        self.fn = fn

    def check(self, values: Dict[str, Any]) -> bool:
        return self.fn(values)


class AndConstraint(Constraint):
    def __init__(self, a: Constraint, b: Constraint):
        super().__init__(f"{a.name} AND {b.name}", min(a.priority, b.priority))
        self.a, self.b = a, b

    def check(self, values: Dict[str, Any]) -> bool:
        return self.a.check(values) and self.b.check(values)


class OrConstraint(Constraint):
    def __init__(self, a: Constraint, b: Constraint):
        super().__init__(f"{a.name} OR {b.name}", min(a.priority, b.priority))
        self.a, self.b = a, b

    def check(self, values: Dict[str, Any]) -> bool:
        return self.a.check(values) or self.b.check(values)


class NotConstraint(Constraint):
    def __init__(self, inner: Constraint):
        super().__init__(f"NOT {inner.name}", inner.priority)
        self.inner = inner

    def check(self, values: Dict[str, Any]) -> bool:
        return not self.inner.check(values)
