"""Sim end-to-end campaign (Harbor → landing → ingest → store → labeling → ERBVE).

One command, full pipeline truth-check with SIMULATED agent runs. Everything the
instrument claims to chain, exercised for real — only the LLM execution body is
simulated. The point: if any seam lies, this script fails.

Usage: python scripts/act1/sim_campaign.py --workdir /tmp/simact1 [--family claude codex ...]
Exit 0 only if every seam passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from harbor_runner.run import AgentSpec, Budget, run_batch
from harness.figures import Taxonomy, erbve_curve, headline
from labeling.runner import ruleset_content_hash, run_labeling
from prereg.ledger import anchor_entry, append_entry
from store.validate import validate_store

FAMILIES = {
    "claude-code": AgentSpec(name="claude-code", version="2.1.0", model_name="claude-sonnet-4-6", model_family="claude", scaffold_version="0.20.0"),
    "codex": AgentSpec(name="codex", version="1.9.0", model_name="gpt-5.2-codex", model_family="openai", scaffold_version="0.20.0"),
    "openhands": AgentSpec(name="openhands", version="0.9.0", model_name="openhands-lm", model_family="openhands", scaffold_version="0.20.0"),
}

TASKS = [
    {
        "instance_id": f"sim-task-{i}",
        "repo_full_name": "django/django",
        "commit_sha": "c" * 40,
        "f2p_tests": [f"tests/sim{i}.py::test_x"],
    }
    for i in range(9)
]


def atif_to_deposit(traj_path: Path, source_id: str, source_class: str, out_path: Path) -> None:
    """Convert one ATIF trajectory into a `.deposit.json` record for ingest."""
    t = json.loads(traj_path.read_text())
    extra = t["extra"]
    attempt = extra["attempt"]
    prov = extra["provenance"]
    # sim derivative patch: pedigree-tokened diff, deterministic per trajectory
    patch_diff = (
        "diff --git a/sim.py b/sim.py\n--- a/sim.py\n+++ b/sim.py\n@@ -1 +1 @@\n"
        f"-# {attempt['task_id'][:8]}\n+# {t['session_id']}\n"
    )
    record = {
        "task": {
            "repo_full_name": "django/django",
            "commit_sha": "c" * 40,
            "f2p_tests": attempt["f2p_tests"],
        },
        "patch_diff": patch_diff,
        "env_fingerprint": attempt["env_fingerprint"],
        "attempt_start": t["steps"][1]["timestamp"],
        "attempt_end": t["steps"][2]["timestamp"] if len(t["steps"]) > 2 else t["steps"][1]["timestamp"],
        "raw_test_output_ref": f"landing://{traj_path.name}#step2.observation",
        "raw_test_output": t["steps"][1]["observation"]["results"][0]["content"],
        "provenance": {
            "model_family": prov["model_family"],
            "model_version": prov["model_version"],
            "scaffold_name": prov["scaffold_name"],
            "scaffold_version": prov["scaffold_version"],
        },
        "source_id": source_id,
        "source_class": source_class,
    }
    out_path.write_text(json.dumps({"record": record}, indent=2, sort_keys=True))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workdir", required=True)
    p.add_argument("--family", nargs="*", default=list(FAMILIES))
    args = p.parse_args()

    workdir = Path(args.workdir)
    landing = workdir / "landing"
    store = workdir / "store"
    ledger = store / "prereg-ledger.jsonl"
    store.mkdir(parents=True, exist_ok=True)

    # 0) Pre-anchor the ruleset on the ledger BEFORE any run (precedence fixture)
    append_entry(
        ledger,
        anchor_entry("x" * 64, ruleset_content_hash(), "2026-08-04T10:00:00Z", "proofs/sim.ots"),
    )

    # 1) Harbor sim runs (one per family), budget-capped
    total_deposited = 0
    for fam in args.family:
        res = run_batch(
            TASKS,
            FAMILIES[fam],
            landing / "harbor",
            Budget(cap_usd=0.20),
            simulate=True,
            source_id="own-harbor-seed",
        )
        total_deposited += res.deposited
        assert not res.stopped_by_budget, f"budget cap hit too early for family {fam}"

    # 2) ATIF → deposit records (the adapter seam, made explicit)
    dep_dir = landing / "deposits"
    count = 0
    for traj in landing.rglob("sim-*.json"):
        if traj.name.endswith(".deposit.json"):
            continue  # replay same command = idempotent; deposits are not trajectories
        out = dep_dir / traj.parent.name / f"{traj.stem}.deposit.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        atif_to_deposit(traj, "own-harbor-seed", "own_harbor_run", out)
        count += 1
    assert count == total_deposited, f"adapter drop: {count} records for {total_deposited} trajectories"

    # 3) Ingest: normalize + dedup + write canonical snapshot + inline validate
    from traces_ingest.normalize import normalize_landing, write_canonical_snapshot

    rep = normalize_landing(dep_dir)
    assert rep.accepted, "normalize accepted nothing"
    assert not rep.rejected, f"normalize rejected: {rep.rejected[:3]}"

    write_canonical_snapshot(
        rep,
        store,
        store_snapshot="sim-" + sha256(str(workdir).encode()).hexdigest()[:12],
        code_commit="simcommit",
        artifact_id="act1-sim",
    )

    # 4) Label the canonical attempts (real ruleset), quarantine cap discipline
    labels_in = [
        {
            "attempt_id": a.attempt_id,
            "task_id": a.task_id,
            "start": a.attempt_window["start"],
            "source_class": a.source_class,
            "raw_output": a.raw_test_output or "",
        }
        for a in rep.accepted
    ]
    res = run_labeling(
        labels_in,
        store_root=store,
        run_id="sim-run-1",
        store_snapshot="sim-snap",
        code_commit="simcommit",
        now_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    print(f"labeled: {res.summary['labels']}  quarantined: {res.summary['quarantined']}")
    assert res.summary["quarantine_share"] <= 0.10

    # 5) Store must validate clean end-to-end (meta, hashes, ownership, precedence)
    rep_val = validate_store(store)
    assert rep_val.ok, rep_val.errors
    assert rep_val.checks.get("prereg-precedence") == "ok"

    # 6) ERBVE figure from the labels (the ACTUAL outputs, not toy fixtures)
    labels = _read_labels(store)
    task_of = {a.attempt_id: a.task_id for a in rep.accepted}
    start_of = {a.attempt_id: a.attempt_window["start"] for a in rep.accepted}
    series_of = {a.attempt_id: (a.provenance["model_family"], "2026") for a in rep.accepted}
    taxonomy = Taxonomy(
        claim_series=frozenset({(FAMILIES[f].model_family, "2026") for f in args.family}),
        context_series=frozenset(),
    )
    fig = erbve_curve(labels, task_of_attempt=task_of.get, start_of_attempt=start_of.get, series_of_attempt=series_of.get, taxonomy=taxonomy)
    print("headline:", headline(fig))
    print("claim line:", fig["claim_line"])
    ledger_lines = ledger.read_text().strip().splitlines()
    assert len(ledger_lines) >= 2, "ledger must hold anchor + run rows"
    print(f"ledger rows: {len(ledger_lines)} (anchor + run)")
    print("SIM CAMPAIGN OK — pipeline truth-checked end-to-end on sim data.")
    return 0


def _read_labels(store: Path) -> list[dict]:
    """Read label ROWS only — manifest/.landing files are not labels."""
    out = []
    for f in store.rglob("labels-*.json"):
        if ".staging" in f.parts or "manifests" in f.parts or f.name == ".landing-manifest.json":
            continue
        out.extend(json.loads(f.read_text()))
    return out


if __name__ == "__main__":
    sys.exit(main())
