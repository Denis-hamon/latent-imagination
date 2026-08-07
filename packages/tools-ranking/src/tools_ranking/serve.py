"""Ranking deployment wiring (story 8.2 + CR, AD-1): the tool deploys EXACTLY
like the advisory gate — pinned snapshot port, deployer-local log, early log
validation, latency measured, OQ-10 tier resolution for REAL (abstention
included), zero patch execution surface.

A ranking refusal/abstention is logged too: the log is the only place a
deployer can see one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core_schema.errors import SchemaError
from core_schema.events import StoreEvent
from gate.decision_log import _inside_store_root, append_decision
from gate.ports import PinnedSnapshot, load_pinned_snapshot
from gate.predict import PinnedPredictor

from tools_ranking.core import Ranked, rank_candidates

INTERFACE_VERSION = "gate-iface-v1"  # the ranking rides the gate's seam version


@dataclass
class RankingServer:
    snapshot: PinnedSnapshot
    predictor: PinnedPredictor
    log_path: Path
    user_test_selection: str | None = None

    @classmethod
    def load(cls, snapshot_root: Path, *, expected_predictor_hash: str, log_path: Path,
             user_test_selection: str | None = None) -> RankingServer:
        snap = load_pinned_snapshot(snapshot_root, expected_predictor_hash=expected_predictor_hash)
        log = Path(log_path)
        if log.name != "decisions.jsonl":
            raise SchemaError("LI-GATE-003", "decision log must be named decisions.jsonl",
                              {"got": str(log)})
        if _inside_store_root(log):
            raise SchemaError("LI-GATE-004", "no writes inside a store root (AD-4)",
                              {"path": str(log)})
        return cls(snapshot=snap, predictor=PinnedPredictor.from_snapshot(snap),
                   log_path=log, user_test_selection=user_test_selection)

    def _event(self, kind: str, payload: dict) -> StoreEvent:
        return StoreEvent(schema_version=1, kind=kind,
                          occurred_at=datetime.now(UTC), payload=payload)

    def rank(self, candidates: list[dict], *, prediction_target_tier: str | None) -> list[Ranked]:
        """OQ-10 for real: no tier → NO ranking; the abstention is recorded."""
        if prediction_target_tier not in ("diff_touched", "user_designated"):
            ev = self._event("prediction_refused", {
                "interface_version": INTERFACE_VERSION,
                "predictor_hash": self.snapshot.predictor_hash,
                "corpus_version": self.snapshot.corpus_version,
                "candidate_count": len(candidates) if isinstance(candidates, list) else None,
                "reason": "no prediction-target tier (OQ-10)",
                "surface": "ranking",
            })
            append_decision(self.log_path, ev)
            raise SchemaError("LI-RANK-002", "ranking abstains without a prediction-target tier",
                              {"tier": prediction_target_tier})

        t0 = time.perf_counter()
        rows = rank_candidates(self.predictor, candidates)
        latency = time.perf_counter() - t0
        n_tie_groups = len({r.rank for r in rows if r.tie_group})
        ev = self._event("candidates_ranked", {
            "interface_version": INTERFACE_VERSION,
            "n_candidates": len(rows),
            "ranking": [{"candidate_id": r.candidate_id, "score": r.score, "rank": r.rank,
                         "tie_group": r.tie_group, "tie_break": r.tie_break,
                         "patch_sha256": r.patch_sha256} for r in rows],
            "tie_group_count": n_tie_groups,
            "latency_s": round(latency, 6),
            "predictor_hash": self.snapshot.predictor_hash,
            "predictor_version": self.snapshot.predictor_version,
            "corpus_version": self.snapshot.corpus_version,
            "prediction_target_tier": prediction_target_tier,
            "predictor_disclosure": (self.snapshot.manifest.get("measured") or {}),
        })
        append_decision(self.log_path, ev)
        return rows
