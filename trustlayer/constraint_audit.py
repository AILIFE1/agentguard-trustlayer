"""ConstraintAudit — tracks constraint set evolution over time.

Hashes the active constraint set at each record() call, chains hashes like
Cathedral's snapshot chain, and computes drift from the original baseline.
Detects permissiveness drift (constraints being removed or weakened by name).
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from trustlayer.constraints import Constraint


class ConstraintAudit:
    """Tamper-evident audit trail for a Validator's constraint set.

    Usage::

        audit = ConstraintAudit(initial_constraints)
        # ... later, after constraints change ...
        audit.record(new_constraints)
        print(audit.drift())
    """

    def __init__(self, constraints: List["Constraint"]):
        self._last_hash = "GENESIS"
        self._history: List[Dict] = []
        snap = self._snapshot(constraints)
        snap["label"] = "baseline"
        self._history.append(snap)
        self._last_hash = snap["hash"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, constraints: List["Constraint"], label: str = "") -> str:
        """Hash the current constraint set and append to the chain.

        Returns the new hash.
        """
        snap = self._snapshot(constraints)
        if label:
            snap["label"] = label
        self._history.append(snap)
        self._last_hash = snap["hash"]
        return snap["hash"]

    def drift(self) -> Dict:
        """Return divergence metrics vs the baseline snapshot."""
        baseline = self._history[0]
        current  = self._history[-1]

        baseline_names = set(baseline["names"])
        current_names  = set(current["names"])

        removed = baseline_names - current_names
        added   = current_names - baseline_names

        total      = max(len(baseline_names), 1)
        divergence = round(len(removed | added) / total, 4)

        counts = [s["count"] for s in self._history]
        if len(counts) >= 2 and counts[-1] < counts[0]:
            trend = "permissive_drift"
        elif divergence > 0:
            trend = "changed"
        else:
            trend = "stable"

        return {
            "divergence_from_baseline": divergence,
            "trend": trend,
            "baseline_count": baseline["count"],
            "current_count": current["count"],
            "removed_constraints": sorted(removed),
            "added_constraints":   sorted(added),
            "snapshots": len(self._history),
            "baseline_hash": baseline["hash"][:16],
            "current_hash":  current["hash"][:16],
            "unchanged": divergence == 0.0 and current["hash"] == baseline["hash"],
        }

    def history(self) -> List[Dict]:
        """Full snapshot history (oldest first)."""
        return list(self._history)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _snapshot(self, constraints: List["Constraint"]) -> Dict:
        names = sorted(c.name for c in constraints)
        payload = json.dumps(
            {"names": names, "prev": self._last_hash},
            sort_keys=True,
        ).encode()
        h = hashlib.sha256(payload).hexdigest()
        return {
            "hash":      h,
            "prev_hash": self._last_hash,
            "names":     names,
            "count":     len(constraints),
            "timestamp": time.time(),
            "label":     "",
        }
