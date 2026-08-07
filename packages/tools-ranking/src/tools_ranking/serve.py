"""Ranking deployment wiring (story 8.2, AD-1): the tool deploys EXACTLY like
the advisory gate — pinned snapshot read port, deployer-local decision log,
zero patch execution anywhere in the package (FR-19's posture extends to
planning).

OQ-10: the ranking call consumes the SAME prediction-target policy resolution
as the gate (diff_touched → user_designated → abstain).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core_schema.errors import SchemaError
from core_schema.events import StoreEvent
from gate.decision_log import append_decision
from gate.ports import PinnedSnapshot, load_pinned_snapshot
from gate.predict import PinnedPredictor

from tools_ranking.core import Ranked, rank_candidates

LOG_NAME = "decisions.jsonl"


@dataclass
class RankingServer:
    snapshot: PinnedSnapshot
    predictor: PinnedPredictor
    log_path: Path

    @classmethod
    def load(cls, snapshot_root: Path, *, expected_predictor_hash: str, log_path: Path) -> RankingServer:
        snap = load_pinned_snapshot(snapshot_root, expected_predictor_hash=expected_predictor_hash)
        return cls(snapshot=snap, predictor=PinnedPredictor.from_snapshot(snap), log_path=Path(log_path))

    def rank(self, candidates: list[dict]) -> list[Ranked]:
        """N≥2 candidates. score = pinned predictor; result is LOGGED as a
        Trace-Schema event on the deployer's disk. Executing patches: not here,
        not anywhere in this package (construction absence — test proves it)."""
        if not isinstance(candidates, list):
            raise SchemaError("LI-RANK-002", "candidates must be a list", {})
        rows = rank_candidates(self.predictor, candidates)
        ev = StoreEvent(
            schema_version=1,
            kind="candidates_ranked",
            occurred_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            payload={
                "n_candidates": len(rows),
                "ranking": [r.candidate_id for r in rows],
                "tie_groups": sum(1 for r in rows if r.tie_group),
                "predictor_hash": self.snapshot.predictor_hash,
                "corpus_version": self.snapshot.corpus_version,
            },
        )
        append_decision(self.log_path, ev)
        return rows
