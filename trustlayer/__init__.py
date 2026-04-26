"""TrustLayer — deterministic validation engine for AI and autonomous systems."""

import logging

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)

from trustlayer.auth import AuthorityLevel, AuthToken
from trustlayer.constraints import (
    AndConstraint,
    Constraint,
    LambdaConstraint,
    NotConstraint,
    OrConstraint,
)
from trustlayer.engine import Agent, AsyncModel, Cathedral, RetryConfig, parse_action
from trustlayer.types import Action, State, Update
from trustlayer.validator import ValidationEvent, Validator

__all__ = [
    "AuthorityLevel",
    "AuthToken",
    "Constraint",
    "LambdaConstraint",
    "AndConstraint",
    "OrConstraint",
    "NotConstraint",
    "State",
    "Action",
    "Update",
    "ValidationEvent",
    "Validator",
    "Agent",
    "AsyncModel",
    "Cathedral",
    "RetryConfig",
    "parse_action",
]

__version__ = "2.0.0"
