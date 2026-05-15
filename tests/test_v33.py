"""Tests for TrustLayer v3.3 features:
  - Constraint authorship (block, author, reason)
  - Block-shape clustering in ConstraintAudit
  - Gate diagnostics on ValidationEvent
  - ExternalCallConfig type
  - ProvenanceVerifier / HttpVerifier / CathedralVerifier
"""
import secrets
import pytest

from trustlayer import (
    Action,
    AuthorityLevel,
    AuthToken,
    ConstraintAudit,
    ExternalCallConfig,
    GateDiagnostic,
    LambdaConstraint,
    State,
    Update,
    ValidationEvent,
    Validator,
    HttpVerifier,
    CathedralVerifier,
    ProvenanceVerifier,
)
from trustlayer.constraints import Constraint


SECRET = secrets.token_bytes(32)


def _token(ttl=60):
    return AuthToken.issue(AuthorityLevel.USER, "test", ttl, SECRET)


def _validator(constraints, verifier=None):
    state = State({"balance": 100, "status": "active"})
    return Validator(state, constraints, SECRET, verifier=verifier)


# ---------------------------------------------------------------------------
# Constraint authorship
# ---------------------------------------------------------------------------

class TestConstraintAuthorship:
    def test_defaults_empty(self):
        c = Constraint("no-op")
        assert c.block == ""
        assert c.author == ""
        assert c.reason == ""

    def test_fields_set(self):
        c = LambdaConstraint(
            "balance cap",
            lambda v: v["balance"] <= 1000,
            block="resource",
            author="alice",
            reason="prevents overdraft",
        )
        assert c.block == "resource"
        assert c.author == "alice"
        assert c.reason == "prevents overdraft"

    def test_backward_compat_positional(self):
        c = LambdaConstraint("name", lambda v: True, 50)
        assert c.priority == 50
        assert c.block == ""

    def test_block_keyword_only(self):
        with pytest.raises(TypeError):
            LambdaConstraint("x", lambda v: True, 100, "resource")  # block must be kw


# ---------------------------------------------------------------------------
# Block-shape clustering
# ---------------------------------------------------------------------------

class TestBlockShapeClustering:
    def _constraints(self):
        return [
            LambdaConstraint("balance <= 1000", lambda v: v.get("balance", 0) <= 1000,
                             block="resource", author="alice"),
            LambdaConstraint("status active",   lambda v: v.get("status") == "active",
                             block="identity",  author="bob"),
            LambdaConstraint("rate limit",      lambda v: True,
                             block="resource",  author="alice"),
        ]

    def test_block_drift_present_in_drift(self):
        audit = ConstraintAudit(self._constraints())
        d = audit.drift()
        assert "block_drift" in d

    def test_block_drift_stable_when_unchanged(self):
        cs = self._constraints()
        audit = ConstraintAudit(cs)
        audit.record(cs)
        d = audit.drift()
        for blk, info in d["block_drift"].items():
            assert info["trend"] == "stable"
            assert info["divergence"] == 0.0

    def test_block_drift_detects_resource_removal(self):
        cs = self._constraints()
        audit = ConstraintAudit(cs)
        # remove one resource constraint
        reduced = [c for c in cs if c.name != "rate limit"]
        audit.record(reduced)
        d = audit.drift()
        resource = d["block_drift"]["resource"]
        assert "rate limit" in resource["removed"]
        assert resource["trend"] == "permissive_drift"

    def test_unblocked_group(self):
        cs = [LambdaConstraint("no block", lambda v: True)]
        audit = ConstraintAudit(cs)
        d = audit.drift()
        assert "_unblocked" in d["block_drift"]

    def test_block_counts(self):
        cs = self._constraints()
        audit = ConstraintAudit(cs)
        d = audit.drift()
        assert d["block_drift"]["resource"]["baseline_count"] == 2
        assert d["block_drift"]["identity"]["baseline_count"] == 1


# ---------------------------------------------------------------------------
# Authorship tracking in ConstraintAudit
# ---------------------------------------------------------------------------

class TestAuthorshipTracking:
    def test_no_changes_empty_list(self):
        cs = [LambdaConstraint("c", lambda v: True, author="alice")]
        audit = ConstraintAudit(cs)
        audit.record(cs)
        assert audit.drift()["authorship_changes"] == []

    def test_authorship_change_detected(self):
        c1 = LambdaConstraint("c", lambda v: True, author="alice")
        audit = ConstraintAudit([c1])
        c2 = LambdaConstraint("c", lambda v: True, author="bob")
        audit.record([c2])
        assert "c" in audit.drift()["authorship_changes"]

    def test_added_constraint_not_in_authorship_changes(self):
        c1 = LambdaConstraint("c1", lambda v: True, author="alice")
        audit = ConstraintAudit([c1])
        c2 = LambdaConstraint("c2", lambda v: True, author="bob")
        audit.record([c1, c2])
        assert "c2" not in audit.drift()["authorship_changes"]


# ---------------------------------------------------------------------------
# Gate diagnostics
# ---------------------------------------------------------------------------

class TestGateDiagnostics:
    def test_diagnostics_empty_on_success(self):
        c = LambdaConstraint("always true", lambda v: True)
        v = _validator([c])
        update = Update("test", [Action("set", "balance", 50)], _token())
        event = v.validate_update(update)
        assert event.success
        assert event.diagnostics == []

    def test_diagnostics_populated_on_failure(self):
        c = LambdaConstraint(
            "balance cap",
            lambda v: v["balance"] <= 1000,
            block="resource",
            author="alice",
            reason="prevents overdraft",
        )
        v = _validator([c])
        update = Update("set high", [Action("set", "balance", 9999)], _token())
        event = v.validate_update(update)
        assert not event.success
        assert len(event.diagnostics) == 1
        d = event.diagnostics[0]
        assert d.constraint_name == "balance cap"
        assert d.block == "resource"
        assert d.author == "alice"
        assert d.reason == "prevents overdraft"
        assert d.action_type == "set"
        assert d.target_key == "balance"

    def test_multiple_failed_constraints_all_in_diagnostics(self):
        cs = [
            LambdaConstraint("cap A", lambda v: v["balance"] <= 500),
            LambdaConstraint("cap B", lambda v: v["balance"] <= 200),
        ]
        v = _validator(cs)
        update = Update("big set", [Action("set", "balance", 9999)], _token())
        event = v.validate_update(update)
        assert len(event.diagnostics) == 2
        names = {d.constraint_name for d in event.diagnostics}
        assert names == {"cap A", "cap B"}

    def test_diagnostics_is_gatediagnostic_instances(self):
        c = LambdaConstraint("c", lambda v: False)
        v = _validator([c])
        update = Update("fail", [Action("set", "balance", 0)], _token())
        event = v.validate_update(update)
        assert all(isinstance(d, GateDiagnostic) for d in event.diagnostics)


# ---------------------------------------------------------------------------
# ExternalCallConfig
# ---------------------------------------------------------------------------

class TestExternalCallConfig:
    def test_defaults(self):
        cfg = ExternalCallConfig(endpoint="https://api.example.com/pay")
        assert cfg.method == "GET"
        assert cfg.payload == {}
        assert cfg.timeout == 10

    def test_full(self):
        cfg = ExternalCallConfig(
            endpoint="https://api.example.com/pay",
            method="POST",
            payload={"amount": 50},
            timeout=3,
        )
        assert cfg.method == "POST"
        assert cfg.payload == {"amount": 50}

    def test_external_call_action_with_config(self):
        cfg = ExternalCallConfig(endpoint="https://api.example.com/pay", method="POST")
        action = Action(type="external_call", target="payment", value=cfg)
        assert isinstance(action.value, ExternalCallConfig)
        assert action.value.endpoint == "https://api.example.com/pay"

    def test_external_call_accepted_by_default_verifier(self):
        c = LambdaConstraint("always ok", lambda v: True)
        v = _validator([c])
        cfg = ExternalCallConfig(endpoint="https://example.com", method="POST")
        update = Update("call", [Action("external_call", "x", cfg)], _token())
        event = v.validate_update(update)
        assert event.success

    def test_external_call_rejected_when_verifier_returns_false(self):
        from trustlayer.validator import Verifier
        class RejectAll(Verifier):
            def verify(self, action):
                return False
        c = LambdaConstraint("always ok", lambda v: True)
        state = State({"x": 0})
        v = Validator(state, [c], SECRET, verifier=RejectAll())
        cfg = ExternalCallConfig(endpoint="https://example.com")
        update = Update("call", [Action("external_call", "x", cfg)], _token())
        event = v.validate_update(update)
        assert not event.success
        assert "verifier rejected" in event.failed_constraint


# ---------------------------------------------------------------------------
# ProvenanceVerifier subclassing
# ---------------------------------------------------------------------------

class TestProvenanceVerifier:
    def test_abstract_raises(self):
        v = ProvenanceVerifier()
        with pytest.raises(NotImplementedError):
            v.verify(Action("external_call", "x"))

    def test_http_verifier_rejects_on_error(self):
        v = HttpVerifier(endpoint="http://localhost:19999/nonexistent", timeout=1)
        assert v.verify(Action("external_call", "x")) is False

    def test_cathedral_verifier_rejects_on_error(self):
        v = CathedralVerifier(api_key="bad_key", base_url="http://localhost:19999", timeout=1)
        assert v.verify(Action("external_call", "x")) is False

    def test_http_verifier_passes_config(self):
        cfg = ExternalCallConfig(endpoint="https://example.com/pay", method="POST", payload={"a": 1})
        action = Action("external_call", "payment", cfg)
        v = HttpVerifier(endpoint="http://localhost:19999", timeout=1)
        result = v.verify(action)
        assert isinstance(result, bool)

    def test_cathedral_verifier_with_config(self):
        cfg = ExternalCallConfig(endpoint="https://example.com/pay", method="POST")
        action = Action("external_call", "payment", cfg)
        v = CathedralVerifier(api_key="test_key", base_url="http://localhost:19999", timeout=1)
        result = v.verify(action)
        assert isinstance(result, bool)
