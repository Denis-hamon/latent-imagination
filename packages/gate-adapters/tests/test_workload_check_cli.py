"""The documented workload check end-to-end (story 7.2): synthetic deployer
world (own decisions log + own local store + pinned certificate hand-off),
fail-closed composition of the three legs, reasons printed and recorded."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from gate.testing import make_fixture_certificate, write_certificate_snapshot
from gate_adapters import workload_check as wc

POLICY = "[cadence]\nmax_age_days = 14\n[measurement]\nbinarization_threshold = 0.5\n"


def _sha(s: str) -> str:
    return sha256(s.encode()).hexdigest()


def _world(tmp_path: Path, rows: list[tuple[float, str]]) -> dict:
    """rows: (flip_probability, outcome). One distinct patch per row."""
    store = tmp_path / "store"
    snaps, labels = [], []
    events = []
    for i, (prob, outcome) in enumerate(rows):
        h = _sha(f"fixture-diff-{i}\n")
        snaps.append({"attempt_id": f"att-{i}", "task_id": "t1", "patch_sha256": h})
        labels.append({"attempt_id": f"att-{i}", "task_id": "t1", "outcome": outcome,
                       "schema_version": 1, "ruleset_version": "rules-v1"})
        events.append({"schema_version": 1, "kind": "gate_annotated",
                       "occurred_at": f"2026-08-15T10:{i:02d}:00Z",
                       "payload": {"candidate": {"patch_sha256": h},
                                   "flip_probability": prob,
                                   "prediction_target_tier": "diff_touched"}})
    d = store / "canonical" / "snap-0" / "v0"
    d.mkdir(parents=True)
    (d / "snapshot-snap-0.json").write_text(json.dumps(snaps))
    dl = store / "labels" / "labels-000" / "v0"
    dl.mkdir(parents=True)
    (dl / "labels-rules-v1.json").write_text(json.dumps(labels))
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    cert = make_fixture_certificate(0.93)  # above-bar fixture certificate
    cert_dir = tmp_path / "cert-snapshot"
    pin = write_certificate_snapshot(cert_dir, [cert], cert)
    policy = tmp_path / "policy.toml"
    policy.write_text(POLICY)
    return {"store": store, "decisions": decisions, "cert": cert_dir,
            "pin": pin, "policy": policy, "report": tmp_path / "report.json"}


def _run(w: dict, *, generation: str = "probe-gen-a", now: str | None = None,
         cert_dir=None, pin=None, store=None, decisions=None) -> int:
    argv = ["--decisions", str(decisions or w["decisions"]),
            "--store-root", str(store or w["store"]),
            "--cert-snapshot", str(cert_dir or w["cert"]),
            "--cert-pin", pin or w["pin"],
            "--generation", generation,
            "--policy", str(w["policy"]),
            "--report", str(w["report"])]
    if now:
        argv += ["--now", now]
    return wc.main(argv)


def _last_event(w: dict) -> dict:
    lines = [l for l in w["decisions"].read_text().splitlines() if l.strip()]
    return json.loads(lines[-1])


def _rows_high() -> list[tuple[float, str]]:
    return [(0.9, "valid_execution")] * 9 + [(0.9, "false_start_tests_ran_no_flip")]


def _rows_subbar() -> list[tuple[float, str]]:
    return [(0.9, "valid_execution")] * 5 + [(0.9, "false_start_tests_ran_no_flip")] * 3


class TestCheckVerdicts:
    def test_subbar_local_precision_keeps_advisory_with_reason(self, tmp_path, capsys):
        w = _world(tmp_path, _rows_subbar())  # precision 5/8 = 0.625 < bar
        assert _run(w) == 0
        out = capsys.readouterr().out
        assert "ADVISORY" in out
        report = json.loads(w["report"].read_text())
        assert report["verdict"]["blocking_enabled"] is False
        assert "at/below bar" in report["verdict"]["reason"]
        assert report["measurement"]["precision"] == pytest.approx(0.625)
        ev = _last_event(w)
        assert ev["kind"] == "workload_checked"
        assert ev["payload"]["blocking_enabled"] is False
        assert "no workload check on record" in report["prior_check_freshness"]["reason"]

    def test_above_bar_local_precision_enables_blocking(self, tmp_path, capsys):
        w = _world(tmp_path, _rows_high())  # precision 0.9 > 0.8889
        assert _run(w) == 0
        out = capsys.readouterr().out
        assert "BLOCKING ENABLED" in out
        report = json.loads(w["report"].read_text())
        assert report["verdict"]["blocking_enabled"] is True
        assert report["verdict"]["reason"].startswith("local workload precision")
        ev = _last_event(w)
        assert ev["payload"]["blocking_enabled"] is True
        assert ev["payload"]["registered_bar"] == pytest.approx(0.8889)

    def test_generation_outside_certified_set_keeps_blocking_off(self, tmp_path):
        w = _world(tmp_path, _rows_high())
        assert _run(w, generation="unseen-model-gen") == 0
        report = json.loads(w["report"].read_text())
        assert report["verdict"]["blocking_enabled"] is False
        assert "re-probe" in report["verdict"]["reason"]
        ev = _last_event(w)
        assert ev["payload"]["blocking_enabled"] is False
        assert ev["payload"]["certificate_hash"] == w["pin"]  # what was asked about

    def test_invalid_pin_is_a_hard_invocation_error(self, tmp_path, capsys):
        w = _world(tmp_path, _rows_high())
        assert _run(w, pin="not-a-pin") == 3
        out = capsys.readouterr().out
        assert "LI-GATE-006" in out

    def test_missing_store_fails_coded(self, tmp_path):
        w = _world(tmp_path, _rows_high())
        assert _run(w, store=w["store"].parent / "nowhere") == 3


class TestFreshnessLeg:
    def test_expired_prior_check_is_reported_stale(self, tmp_path):
        w = _world(tmp_path, _rows_high())
        assert _run(w, now="2026-08-15T12:00:00Z") == 0
        # 30 days later: the recorded check is beyond max_age_days=14
        assert _run(w, now="2026-09-15T12:00:00Z") == 0
        report = json.loads(w["report"].read_text())
        assert report["prior_check_freshness"]["blocking_permitted"] is False
        assert "expired" in report["prior_check_freshness"]["reason"]

    def test_fresh_prior_check_permits(self, tmp_path):
        w = _world(tmp_path, _rows_high())
        assert _run(w, now="2026-08-15T12:00:00Z") == 0
        assert _run(w, now="2026-08-20T12:00:00Z") == 0
        report = json.loads(w["report"].read_text())
        assert report["prior_check_freshness"]["blocking_permitted"] is True


class TestConfidenceNeverAnInput:
    def test_measurement_identical_with_or_without_smuggled_confidence(self, tmp_path):
        base, smuggled = tmp_path / "base", tmp_path / "smuggled"
        base.mkdir()
        smuggled.mkdir()
        wb = _world(base, _rows_high())
        ws = _world(smuggled, _rows_high())
        # every annotation in the smuggled world carries confidence fields
        events = []
        for line in ws["decisions"].read_text().splitlines():
            ev = json.loads(line)
            ev["payload"]["confidence"] = 0.99
            ev["payload"]["confidence_tier"] = "high"
            events.append(json.dumps(ev))
        ws["decisions"].write_text("\n".join(events) + "\n")
        assert _run(wb) == 0
        assert _run(ws) == 0
        mb = json.loads(wb["report"].read_text())["measurement"]
        ms = json.loads(ws["report"].read_text())["measurement"]
        assert mb == ms  # the smuggled fields changed NOTHING
        assert "confidence" not in json.dumps(mb)
