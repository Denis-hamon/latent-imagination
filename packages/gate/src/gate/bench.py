"""Latency proof harness (story 5.4, NFR-P1/OQ-3): measures the SERVE path —
real predictions through GateServer handles — never a raw microbenchmark.

Budget comes from the committed policy file (TOML); a miss yields the
annotations-async verdict, never a green-wash (SM-C3 posture).
"""

from __future__ import annotations

import statistics
import time
import tomllib
from pathlib import Path

from core_schema.errors import SchemaError


def load_budget(path: Path) -> float:
    """Same fail-closed rigor as the artifact gates (CR 5.4: no bool/nan/inf)."""
    import math

    try:
        data = tomllib.loads(Path(path).read_bytes().decode("utf-8"))
    except FileNotFoundError as exc:
        raise SchemaError("LI-GATE-007", "latency budget file missing", {"path": str(path)}) from exc
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-GATE-007", "latency budget unparseable", {"path": str(path)}) from exc
    raw = (data.get("budget") or {}).get("p95_seconds") if isinstance(data.get("budget"), dict) else None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise SchemaError("LI-GATE-007", "latency budget must be a number", {"got": raw})
    v = float(raw)
    if not math.isfinite(v) or v <= 0:
        raise SchemaError("LI-GATE-007", "latency budget must be finite and positive", {"got": v})
    return v


def percentile(sorted_xs: list[float], q: float) -> float:
    """Nearest-rank-on-sorted; q in (0,100]. Deterministic, documented."""
    if not sorted_xs:
        raise SchemaError("LI-GATE-007", "percentile of empty sample", {})
    if sorted_xs != sorted(sorted_xs):
        raise SchemaError("LI-GATE-007", "percentile input must be sorted", {})
    import math

    if not (0 < q <= 100):
        raise SchemaError("LI-GATE-007", "percentile q outside (0,100]", {"got": q})
    k = max(1, math.ceil(q / 100.0 * len(sorted_xs) - 1e-12))  # ulp-guard: exact multiples stay exact
    return sorted_xs[k - 1]


def _percentiles(xs: list[float]) -> dict:
    s = sorted(xs)
    return {"mean_s": statistics.fmean(s), "p50_s": percentile(s, 50),
            "p95_s": percentile(s, 95), "p99_s": percentile(s, 99), "max_s": s[-1]}


def bench_report(server, documents: list[str], ctx_factory, *, hardware_note: str) -> dict:
    """Cold pass (1st touch per doc) then warm repeats; per-prediction latency
    harvested from the emitted annotations (the serve path measures itself).
    The serve OVERHEAD (annotate + decision-log I/O) is timed separately so no
    part of the in-loop cost escapes the published table (CR 5.4)."""
    if not documents or any(not d or not d.strip() for d in documents):
        raise SchemaError("LI-GATE-007", "bench corpus empty or holds a blank doc", {})
    lat_cold: list[float] = []
    overhead_samples: list[float] = []
    for doc in documents:
        ev = server.handle(ctx_factory(doc), prediction_target_tier="diff_touched",
                           model_family="baseline")
        lat_cold.append(ev.payload["latency_s"])
    repeats = max(1, 2000 // len(documents))
    lat_warm: list[float] = []
    for _ in range(repeats):
        for doc in documents:
            t0 = time.perf_counter()
            ev = server.handle(ctx_factory(doc), prediction_target_tier="diff_touched",
                               model_family="baseline")
            total = time.perf_counter() - t0
            lat_warm.append(ev.payload["latency_s"])
            overhead_samples.append(max(total - ev.payload["latency_s"], 0.0))
    return {
        "hardware": hardware_note,
        "predictor_hash": server.snapshot.predictor_hash,
        "corpus_version": server.snapshot.corpus_version,
        "workload": {"docs": len(documents), "max_doc_bytes": max(len(d.encode()) for d in documents),
                      "seed": "embedded fixture (deterministic)"},
        "cold": {"n": len(lat_cold), **_percentiles(lat_cold)},
        "warm": {"n": len(lat_warm), **_percentiles(lat_warm)},
        "serve_overhead": {"n": len(overhead_samples), **_percentiles(overhead_samples)},
    }


def verdict(report: dict, budget_s: float) -> dict:
    """SM-C3: the verdict names reality. A miss ships annotations-async guidance.
    Warm p95 AND cold max both count (CR 5.4: no cold blind spot)."""
    try:
        p95 = float(report["warm"]["p95_s"])
        cold_max = float(report["cold"]["max_s"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SchemaError("LI-GATE-007", "verdict report malformed", {}) from exc
    import math

    if not (math.isfinite(p95) and math.isfinite(cold_max)):
        raise SchemaError("LI-GATE-007", "verdict report holds non-finite latency", {})
    if p95 <= budget_s and cold_max <= budget_s:
        return {"verdict": "meets-budget", "p95_s": p95, "cold_max_s": cold_max, "budget_s": budget_s}
    return {
        "verdict": "annotations-async",
        "p95_s": p95,
        "cold_max_s": cold_max,
        "budget_s": budget_s,
        "guidance": "budget missed on this hardware: run the gate asynchronously and "
                    "surface annotations post-hoc; do NOT quote it as invisible in-loop.",
    }
