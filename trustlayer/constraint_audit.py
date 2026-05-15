"""ConstraintAudit — tracks constraint set evolution over time.

v3.3 additions:
  - Block-shape clustering: drift() breaks down divergence per logical block
    (block="" constraints are grouped under "_unblocked").
  - Authorship tracking: records author/reason per constraint; drift() surfaces
    any constraint whose author changed between baseline and current.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Set

if TYPE_CHECKING:
    from trustlayer.constraints import Constraint


class ConstraintAudit:
    """Tamper-evident audit trail for a Validator's constraint set.

    Usage::

        audit = ConstraintAudit(initial_constraints)
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
        """Hash the current constraint set and append to the chain."""
        snap = self._snapshot(constraints)
        if label:
            snap["label"] = label
        self._history.append(snap)
        self._last_hash = snap["hash"]
        return snap["hash"]

    def drift(self) -> Dict:
        """Return divergence metrics vs the baseline snapshot.

        Keys (all existing keys preserved for backward compatibility):
            divergence_from_baseline  float 0-1
            trend                     "stable" | "changed" | "permissive_drift"
            removed_constraints       list[str]
            added_constraints         list[str]
            baseline_count / current_count
            baseline_hash / current_hash
            snapshots
            unchanged
            block_drift               dict[block -> {divergence, removed, added}]
            authorship_changes        list[str]  constraint names whose author changed
        """
        baseline = self._history[0]
        current  = self._history[-1]

        baseline_names: Set[str] = {e["name"] for e in baseline["entries"]}
        current_names:  Set[str] = {e["name"] for e in current["entries"]}

        removed = baseline_names - current_names
        added   = current_names  - baseline_names

        total      = max(len(baseline_names), 1)
        divergence = round(len(removed | added) / total, 4)

        counts = [s["count"] for s in self._history]
        if len(counts) >= 2 and counts[-1] < counts[0]:
            trend = "permissive_drift"
        elif divergence > 0:
            trend = "changed"
        else:
            trend = "stable"

        # -- block-shape clustering --------------------------------------
        def _by_block(entries: List[Dict]) -> Dict[str, Set[str]]:
            groups: Dict[str, Set[str]] = defaultdict(set)
            for e in entries:
                groups[e["block"] or "_unblocked"].add(e["name"])
            return dict(groups)

        b_blocks = _by_block(baseline["entries"])
        c_blocks = _by_block(current["entries"])
        all_blocks = set(b_blocks) | set(c_blocks)

        block_drift: Dict[str, Dict] = {}
        for blk in sorted(all_blocks):
            b_names = b_blocks.get(blk, set())
            c_names = c_blocks.get(blk, set())
            blk_removed = b_names - c_names
            blk_added   = c_names - b_names
            blk_div     = round(len(blk_removed | blk_added) / max(len(b_names), 1), 4)
            blk_trend   = (
                "permissive_drift" if blk_removed and not blk_added
                else ("changed" if blk_div > 0 else "stable")
            )
            block_drift[blk] = {
                "divergence": blk_div,
                "trend": blk_trend,
                "removed": sorted(blk_removed),
                "added": sorted(blk_added),
                "baseline_count": len(b_names),
                "current_count": len(c_names),
            }

        # -- authorship tracking -----------------------------------------
        b_authors = {e["name"]: e["author"] for e in baseline["entries"]}
        c_authors = {e["name"]: e["author"] for e in current["entries"]}
        authorship_changes = sorted(
            name for name in (baseline_names & current_names)
            if b_authors.get(name) != c_authors.get(name)
        )

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
            "block_drift": block_drift,
            "authorship_changes": authorship_changes,
        }

    def history(self) -> List[Dict]:
        """Full snapshot history (oldest first)."""
        return list(self._history)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _snapshot(self, constraints: List["Constraint"]) -> Dict:
        entries = sorted(
            [
                {
                    "name":   c.name,
                    "block":  getattr(c, "block",  ""),
                    "author": getattr(c, "author", ""),
                    "reason": getattr(c, "reason", ""),
                }
                for c in constraints
            ],
            key=lambda e: e["name"],
        )
        payload = json.dumps(
            {"entries": entries, "prev": self._last_hash},
            sort_keys=True,
        ).encode()
        h = hashlib.sha256(payload).hexdigest()
        return {
            "hash":      h,
            "prev_hash": self._last_hash,
            "entries":   entries,
            "names":     [e["name"] for e in entries],  # backward compat
            "count":     len(entries),
            "timestamp": time.time(),
            "label":     "",
        }
