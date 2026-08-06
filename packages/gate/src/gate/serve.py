"""The wired advisory serve path (story 5.2 AC1): snapshot → pinned predictor →
annotation → decision log. This is the ONLY call chain integrations use.

Latency: every prediction is timed (perf_counter) and the measured value rides
the annotation's latency_s — the decision log IS the latency log (NFR-P1).
Abstention (OQ-10) emits `prediction_refused` instead of annotating.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core_schema.errors import SchemaError
from core_schema.events import StoreEvent

from gate.decision_log import append_decision
from gate.intercept import CandidateCtx, annotate, refuse
from gate.ports import PinnedSnapshot, load_pinned_snapshot
from gate.predict import PinnedPredictor


@dataclass
class GateServer:
    snapshot: PinnedSnapshot
    predictor: PinnedPredictor
    log_path: Path

    @classmethod
    def load(cls, snapshot_root: Path, *, expected_predictor_hash: str, log_path: Path) -> GateServer:
        snap = load_pinned_snapshot(snapshot_root, expected_predictor_hash=expected_predictor_hash)
        return cls(snapshot=snap, predictor=PinnedPredictor.from_snapshot(snap), log_path=Path(log_path))

    def handle(
        self,
        ctx: CandidateCtx,
        *,
        prediction_target_tier: str | None,
        model_family: str,
    ) -> StoreEvent:
        """The one seam: annotate pre-execution, or abstain on the record."""
        if prediction_target_tier is None:
            ev = refuse(self.snapshot, ctx, reason="no test-set denominator (OQ-10 abstain)")
            append_decision(self.log_path, ev)
            return ev
        if not isinstance(ctx.patch_diff, str):  # coded, never a raw TypeError in a hook
            raise SchemaError("LI-GATE-002", "candidate patch must be text", {"got": type(ctx.patch_diff).__name__})
        t0 = time.perf_counter()
        p = self.predictor.score(ctx.patch_diff)
        latency = time.perf_counter() - t0
        ev = annotate(
            self.snapshot, ctx,
            flip_probability=p, model_family=model_family, latency_s=latency,
            disclosure={"measured_precision": self.predictor.measured.get("precision"),
                        "posture": "sub-bar advisory (branch iii)"},
            prediction_target_tier=prediction_target_tier,
        )
        append_decision(self.log_path, ev)
        return ev
