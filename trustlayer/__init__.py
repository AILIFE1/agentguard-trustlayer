"""TrustLayer — deterministic validation engine for AI and autonomous systems."""

import logging

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)

from trustlayer.auth import AuthorityLevel, AuthToken
from trustlayer.constraint_audit import ConstraintAudit
from trustlayer.constraints import (
    AndConstraint,
    Constraint,
    LambdaConstraint,
    NotConstraint,
    OrConstraint,
)
from trustlayer.engine import Agent, AsyncModel, Cathedral, GuardedAgent, RetryConfig, parse_action
from trustlayer.types import Action, ExternalCallConfig, GateDiagnostic, State, Update
from trustlayer.validator import ValidationEvent, Validator
from trustlayer.verifier import CathedralVerifier, HttpVerifier, ProvenanceVerifier

__all__ = [
    "AuthorityLevel",
    "AuthToken",
    "ConstraintAudit",
    "Constraint",
    "LambdaConstraint",
    "AndConstraint",
    "OrConstraint",
    "NotConstraint",
    "State",
    "Action",
    "ExternalCallConfig",
    "GateDiagnostic",
    "Update",
    "ValidationEvent",
    "Validator",
    "Agent",
    "AsyncModel",
    "Cathedral",
    "GuardedAgent",
    "RetryConfig",
    "parse_action",
    "ProvenanceVerifier",
    "HttpVerifier",
    "CathedralVerifier",
]

__version__ = "3.3.0"
