"""The documented workload check (story 7.2, FR-21 c1) — deployer CLI.

Run (5.6 invocation parity — no console script, ``python -m``):

    python -m gate_adapters.workload_check \
        --decisions ~/.latent-imagination/decisions.jsonl \
        --store-root /path/to/local-store \
        --cert-snapshot /path/to/pinned-cert-handoff \
        --cert-pin <64-hex certificate content hash> \
        --generation <deployment's model generation> \
        --report report.json

Composition (fail-closed, FR-21 c1: verdict-hash citation AND per-deployment
check):

  leg 1  gate.blocking.authorize_blocking — certificate pinned + valid +
         generation inside the certified set + certified precision strictly
         above the bar (7.1 seam; LI-GATE-006 on any failure)
  leg 2  gate.workload_check.measure_workload_precision over the rows joined
         from the deployer's OWN log + store — blocking enabled only if LOCAL
         precision is strictly above the bar; at/below keeps advisory and the
         reason is printed (AC)
  leg 3  freshness — the check appends a ``workload_checked`` event to the
         decision log; between runs, ``authorization_state`` expires the
         authorization after ``max_age_days`` (an absent or stale check
         authorizes nothing). The enforcement seam consults it (story 7.3).

Advisory remains the default: this CLI flips no switch in any adapter; it
MEASURES and RECORDS. Exit 0 on every completed check (enabled or not —
hook-law parity); exit 3 on missing/malformed inputs; 2 on bad invocation.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core_schema.errors import SchemaError
from gate.blocking import authorize_blocking
from gate.decision_log import append_decision
from gate.workload_check import (
    CheckVerdict,
    WorkloadRow,
    authorization_state,
    check_against_bar,
    load_workload_policy,
    measure_workload_precision,
    workload_checked_event,
)

from gate_adapters.workload_history import build_workload_history

DEFAULT_POLICY = (Path(__file__).resolve().parents[4]
                  / "governance" / "gate" / "workload-check-policy-v1.toml")


def _parse_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"--now must be ISO-8601: {value!r}") from exc
    if dt.tzinfo is None:
        raise SystemExit("--now must be tz-aware (ISO-8601 with offset/Z)")
    return dt.astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="per-deployment workload check (FR-21)")
    ap.add_argument("--decisions", required=True, type=Path,
                    help="deployer-local decisions.jsonl (the check appends its event here)")
    ap.add_argument("--store-root", required=True, type=Path)
    ap.add_argument("--cert-snapshot", required=True, type=Path,
                    help="pinned hand-off dir: certificate.json + supersession-manifest.json")
    ap.add_argument("--cert-pin", required=True, help="64-hex certificate content hash")
    ap.add_argument("--generation", required=True,
                    help="the deployment NAMES its model generation (fail-closed, no default)")
    ap.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--now", default=None, help="ISO-8601 override (tests)")
    args = ap.parse_args(argv)

    now = _parse_now(args.now)
    if not re.fullmatch(r"[0-9a-f]{64}", args.cert_pin):
        print(json.dumps({"status": "error", "code": "LI-GATE-006",
                          "message": "--cert-pin must be a 64-hex certificate content hash"}))
        return 3
    policy = load_workload_policy(args.policy)
    generation = args.generation

    # leg 1 — certificate authorization (7.1 seam); gives the bar when valid
    leg1_reason: str | None = None
    registered_bar: float | None = None
    certified_precision: float | None = None
    cert_hash = args.cert_pin  # what the caller asked about; refined on success
    try:
        auth = authorize_blocking(args.cert_snapshot,
                                  expected_certificate_hash=args.cert_pin,
                                  query_generation=args.generation)
        registered_bar = auth.registered_bar
        certified_precision = auth.certified_precision
        cert_hash = auth.certificate_hash
    except SchemaError as exc:
        leg1_reason = f"certificate authorization failed ({exc.code}): {exc.message}"

    # leg 2 — local workload precision over the deployer's own history
    try:
        history = build_workload_history(args.decisions, args.store_root)
    except SchemaError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "message": exc.message}))
        return 3

    rows: list[WorkloadRow] = []
    dropped = 0
    for r in history.rows:
        try:
            rows.append(WorkloadRow(**r))
        except (ValueError, TypeError):
            dropped += 1  # builder/protocol drift: strict validation wins
    report_measure = measure_workload_precision(
        rows, binarization_threshold=policy.binarization_threshold)

    if leg1_reason is not None:
        # no valid certificate -> advisory; reason names the failed leg, the bar
        # is honestly recorded as unknown (None), never invented
        verdict = CheckVerdict(blocking_enabled=False, reason=leg1_reason,
                               precision=report_measure.precision,
                               registered_bar=None)
    else:
        verdict = check_against_bar(report_measure, registered_bar=registered_bar)

    # leg 3 — freshness of PRIOR checks (this run appends its own event after)
    prior = authorization_state(_prior_rows(args.decisions),
                                max_age=timedelta(days=policy.max_age_days),
                                now=now)
    event = workload_checked_event(certificate_hash=cert_hash, generation=generation,
                                   report=report_measure, verdict=verdict, policy=policy,
                                   now=now)
    append_decision(args.decisions, event)

    out = {
        "interface_version": event.payload["interface_version"],
        "checked_at": now.isoformat().replace("+00:00", "Z"),
        "certificate": {"pin": args.cert_pin, "certified_precision": certified_precision,
                        "registered_bar": registered_bar, "generation": generation,
                        "authorization_failed_reason": leg1_reason},
        "workload_history": {
            "n_annotations": history.n_annotations, "n_matched": history.n_matched,
            "n_unmatched": history.n_unmatched, "n_ambiguous": history.n_ambiguous,
            "n_abstentions": history.n_abstentions, "n_malformed": history.n_malformed,
            "n_poison_files": history.n_poison_files, "rows_dropped_by_strict_validation": dropped,
        },
        "measurement": {
            "n": report_measure.n, "tp": report_measure.tp, "fp": report_measure.fp,
            "fn": report_measure.fn, "tn": report_measure.tn,
            "precision": report_measure.precision,
            "precision_wilson95": list(report_measure.precision_wilson95)
            if report_measure.precision_wilson95 else None,
            "binarization_threshold": report_measure.binarization_threshold,
            "prediction_target_tiers": list(report_measure.prediction_target_tiers),
        },
        "verdict": {"blocking_enabled": verdict.blocking_enabled, "reason": verdict.reason},
        "policy": {"max_age_days": policy.max_age_days,
                   "binarization_threshold": policy.binarization_threshold},
        "prior_check_freshness": {"blocking_permitted": prior.blocking_permitted,
                                  "reason": prior.reason,
                                  "last_checked_at": prior.last_checked_at},
    }
    # Deployer-local record output via plain open(), the same write style
    # gate.decision_log uses — NOT a canonical-store write (AD-4: the gate
    # family never writes the store; the only shared-state write is the
    # allowlisted append_decision event above).
    args.report.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with args.report.open("w", encoding="utf-8") as fh:
        fh.write(payload)
    status = "BLOCKING ENABLED by workload check" if verdict.blocking_enabled \
        else "ADVISORY (blocking not enabled)"
    print(f"{status}: {verdict.reason}")
    print(f"report: {args.report}")
    return 0


def _prior_rows(decisions: Path) -> list[dict]:
    """Rows already in the log BEFORE this run appends (freshness history)."""
    from gate_adapters.telemetry_etl import load_log

    try:
        records, _ = load_log(decisions)
    except SchemaError:
        return []
    return records


if __name__ == "__main__":
    raise SystemExit(main())
