"""Latency proof harness (story 5.4, NFR-P1/OQ-3): measures the SERVE path —
real predictions through GateServer handles — never a raw microbenchmark.

Budget comes from the committed policy file (TOML); a miss yields the
annotations-async verdict, never a green-wash (SM-C3 posture).
"""

from __future__ import annotations

import statistics
import tomllib
from pathlib import Path

from core_schema.errors import SchemaError


def load_budget(path: Path) -> float:
    try:
        data = tomllib.loads(Path(path).read_bytes().decode("utf-8"))
    except FileNotFoundError as exc:
        raise SchemaError("LI-GATE-007", "latency budget file missing", {"path": str(path)}) from exc
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-GATE-007", "latency budget unparseable", {"path": str(path)}) from exc
    try:
        v = float(data["budget"]["p95_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SchemaError("LI-GATE-007", "latency budget missing [budget].p95_seconds", {}) from exc
    if v <= 0:
        raise SchemaError("LI-GATE-007", "latency budget must be positive", {"got": v})
    return v


def percentile(sorted_xs: list[float], q: float) -> float:
    """Nearest-rank-on-sorted; q in (0,100]. Deterministic, documented."""
    if not sorted_xs:
        raise SchemaError("LI-GATE-007", "percentile of empty sample", {})
    if sorted_xs != sorted(sorted_xs):
        raise SchemaError("LI-GATE-007", "percentile input must be sorted", {})
    import math

    k = max(1, math.ceil(q / 100.0 * len(sorted_xs)))
    return sorted_xs[k - 1]


def bench_report(server, documents: list[str], ctx_factory, *, hardware_note: str) -> dict:
    """Cold pass (1st touch per doc) then warm repeats; per-prediction latency
    harvested from the emitted annotations (the serve path measures itself)."""
    if not documents:
        raise SchemaError("LI-GATE-007", "bench corpus empty", {})
    lat_cold: list[float] = []
    for doc in documents:
        ev = server.handle(ctx_factory(doc), prediction_target_tier="diff_touched",
                           model_family="baseline")
        lat_cold.append(ev.payload["latency_s"])
    repeats = max(1, 2000 // len(documents))
    lat_warm: list[float] = []
    for _ in range(repeats):
        for doc in documents:
            ev = server.handle(ctx_factory(doc), prediction_target_tier="diff_touched",
                               model_family="baseline")
            lat_warm.append(ev.payload["latency_s"])
    lat_warm.sort()
    n = len(lat_warm)
    warm = {
        "n": n,
        "mean_s": statistics.fmean(lat_warm),
        "p50_s": percentile(lat_warm, 50),
        "p95_s": percentile(lat_warm, 95),
        "p99_s": percentile(lat_warm, 99),
    }
    return {
        "hardware": hardware_note,
        "predictor_hash": server.snapshot.predictor_hash,
        "corpus_version": server.snapshot.corpus_version,
        "cold": {"n": len(lat_cold), "max_s": max(lat_cold)},
        "warm": warm,
    }


def verdict(report: dict, budget_s: float) -> dict:
    """SM-C3: the verdict names reality. A miss ships annotations-async guidance."""
    p95 = report["warm"]["p95_s"]
    if p95 <= budget_s:
        return {"verdict": "meets-budget", "p95_s": p95, "budget_s": budget_s}
    return {
        "verdict": "annotations-async",
        "p95_s": p95,
        "budget_s": budget_s,
        "guidance": "budget missed on this hardware: run the gate asynchronously and "
                    "surface annotations post-hoc; do NOT quote it as invisible in-loop.",
    }
