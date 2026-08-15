"""Shadow-sampling report CLI (story 7.4, FR-22 c3). Run via ``python -m``.

Reads a deployer-local shadow-twin log (JSONL), computes SM-C1 (false-block
rate + Wilson 95% CI + sampled share), compares it against the story-7.3
false-block budget, appends an ``sm_c1_reported`` event to the decision log,
and writes a deployer-local report JSON.

AD-4 fence: the report is written via plain ``open().write()`` (never a
``write_text(`` store marker) to a deployer-chosen path, and the only
shared-state write is the allowlisted ``append_decision`` event. The gate
family never writes a canonical store.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from core_schema.errors import SchemaError
from core_schema.events import StoreEvent
from gate.blocking import load_false_block_budget
from gate.decision_log import append_decision
from gate.shadow import (
    SHADOW_IFACE_VERSION,
    BudgetVerdict,
    SMReport,
    compare_against_budget,
    compute_sm_c1,
    load_shadow_policy,
    make_twin,
)

_TWIN_FIELDS = ("patch_sha256", "certificate_hash", "realized_outcome")


def load_samples(path: Path) -> tuple[list, dict]:
    """Stream-read the twin log (never a whole-file slurp, 5.6 lesson).
    BOM-tolerant; torn/poison lines and rows that fail strict ShadowTwin
    validation are COUNTED and skipped, never fatal."""
    p = Path(path)
    if not p.is_file():
        raise SchemaError("LI-GADPT-006", "shadow samples file missing", {"path": str(p)})
    twins: list = []
    stats = {"torn_lines": 0, "rejected_rows": 0, "rows": 0}
    try:
        with p.open(encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                stats["rows"] += 1
                try:
                    obj = json.loads(
                        line, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
                except ValueError:
                    stats["torn_lines"] += 1
                    continue
                if not isinstance(obj, dict) or any(k not in obj for k in _TWIN_FIELDS):
                    stats["rejected_rows"] += 1
                    continue
                try:
                    twins.append(make_twin(obj["patch_sha256"], obj["certificate_hash"],
                                           obj["realized_outcome"]))
                except SchemaError:
                    stats["rejected_rows"] += 1
    except OSError as exc:
        raise SchemaError("LI-GADPT-006", "shadow samples file unreadable",
                          {"path": str(p)}) from exc
    except UnicodeDecodeError as exc:
        raise SchemaError("LI-GADPT-006", "shadow samples file not utf-8",
                          {"path": str(p)}) from exc
    return twins, stats


def sm_c1_event(*, report: SMReport, verdict: BudgetVerdict, policy_rate: float,
                budget_seal: str, max_false_block_rate: float,
                now: datetime | None = None) -> StoreEvent:
    payload = {
        "interface_version": SHADOW_IFACE_VERSION,
        "n_block_decisions": report.n_block_decisions,
        "n_sampled": report.n_sampled,
        "n_false_block": report.n_false_block,
        "false_block_rate": report.false_block_rate,
        "false_block_wilson95": list(report.false_block_wilson95)
        if report.false_block_wilson95 else None,
        "sampled_share": report.sampled_share,
        "shadow_rate_requested": policy_rate,
        "budget_max_false_block_rate": max_false_block_rate,
        "within_budget": verdict.within_budget,
        "reason": verdict.reason,
        "budget_seal_sha256": budget_seal,
    }
    return StoreEvent(schema_version=1, kind="sm_c1_reported",
                      occurred_at=now or datetime.now(UTC), payload=payload)


def _num(v):
    return None if v is None else (None if isinstance(v, float) and (math.isnan(v) or math.isinf(v)) else v)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="shadow-mode SM-C1 report (story 7.4)")
    ap.add_argument("--samples", required=True, type=Path, help="shadow twin log (JSONL)")
    ap.add_argument("--n-block-decisions", required=True, type=int)
    ap.add_argument("--budget", required=True, type=Path, help="7.3 false-block budget TOML")
    ap.add_argument("--policy", required=True, type=Path, help="7.4 shadow policy TOML")
    ap.add_argument("--decisions", required=True, type=Path, help="decisions.jsonl")
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--now", default=None)
    args = ap.parse_args(argv)

    if args.n_block_decisions < 0:
        print(json.dumps({"status": "error", "code": "LI-GADPT-006",
                          "message": "--n-block-decisions must be >= 0"}))
        return 3

    try:
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
        if args.now and now.tzinfo is None:
            raise ValueError("naive")
        now = now.astimezone(UTC) if args.now else now
    except ValueError:
        print(json.dumps({"status": "error", "code": "LI-GADPT-006",
                          "message": "--now must be tz-aware ISO-8601"}))
        return 3

    try:
        policy = load_shadow_policy(args.policy)
        budget = load_false_block_budget(args.budget)
        twins, stats = load_samples(args.samples)
    except SchemaError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "message": exc.message}))
        return 3

    report = compute_sm_c1(twins, n_block_decisions=args.n_block_decisions)
    verdict = compare_against_budget(report, max_false_block_rate=budget.max_false_block_rate)
    append_decision(args.decisions, sm_c1_event(
        report=report, verdict=verdict, policy_rate=policy.shadow_rate,
        budget_seal=budget.seal_sha256,
        max_false_block_rate=budget.max_false_block_rate, now=now))

    out = {
        "interface_version": SHADOW_IFACE_VERSION,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "policy": {"shadow_rate": policy.shadow_rate, "salt": policy.salt},
        "input_stats": stats,
        "sm_c1": {
            "n_block_decisions": report.n_block_decisions,
            "n_sampled": report.n_sampled,
            "n_false_block": report.n_false_block,
            "false_block_rate": _num(report.false_block_rate),
            "false_block_wilson95": list(report.false_block_wilson95)
            if report.false_block_wilson95 else None,
            "sampled_share": _num(report.sampled_share),
        },
        "budget": {"max_false_block_rate": budget.max_false_block_rate,
                   "seal_sha256": budget.seal_sha256},
        "verdict": {"within_budget": verdict.within_budget, "reason": verdict.reason},
        "pilot_disclosure": "phase-4 machinery: this report is computed over the "
                            "deployer-provided twin log (synthetic pilot until a live "
                            "block ships at story 7.5); no live twin execution here",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with args.report.open("w", encoding="utf-8") as fh:
        fh.write(payload)

    status = "WITHIN BUDGET" if verdict.within_budget else "NOT WITHIN BUDGET"
    rate_s = "undefined (none shadowed)" if report.false_block_rate is None \
        else f"{report.false_block_rate:.4f}"
    print(f"SM-C1 {status}: false-block rate {rate_s} vs budget "
          f"{budget.max_false_block_rate:.4f}")
    print(f"reason: {verdict.reason}")
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
