"""Shadow-mode SM-C1 report CLI (story 7.4): pilot demonstration over the
committed synthetic fixture, poison tolerance, budget-seal binding, and the
honest empty/undefined path."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from gate_adapters import shadow_report as sr

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "shadow-pilot-samples.jsonl"

BUDGET_TOML = (
    "[budget]\nmax_false_block_rate = 0.05\n\n"
    "[derivation]\ncost_exec_usd = 0.0025\ncost_regen_usd = 0.0200\n"
    "rationale = \"fixture\"\n"
)
POLICY_TOML = "[sampling]\nshadow_rate = 0.10\nsalt = \"shadow-v1\"\n"


def _world(tmp_path: Path) -> dict:
    budget = tmp_path / "budget.toml"
    budget.write_text(BUDGET_TOML)
    policy = tmp_path / "policy.toml"
    policy.write_text(POLICY_TOML)
    decisions = tmp_path / "deployer" / "decisions.jsonl"
    return {"samples": FIXTURE, "budget": budget, "policy": policy,
            "decisions": decisions, "report": tmp_path / "report.json"}


def _run(w: dict, *, n_blocks: int = 400, samples=None, now="2026-08-15T12:00:00Z") -> int:
    argv = ["--samples", str(samples or w["samples"]),
            "--n-block-decisions", str(n_blocks),
            "--budget", str(w["budget"]), "--policy", str(w["policy"]),
            "--decisions", str(w["decisions"]), "--report", str(w["report"]),
            "--now", now]
    return sr.main(argv)


class TestPilotDemonstration:
    def test_sm_c1_computed_and_within_budget(self, tmp_path, capsys):
        w = _world(tmp_path)
        assert _run(w) == 0
        report = json.loads(w["report"].read_text())
        sm = report["sm_c1"]
        # fixture truth: 40 shadowed blocks, exactly 1 realized valid flip
        assert sm["n_sampled"] == 40
        assert sm["n_false_block"] == 1
        assert sm["false_block_rate"] == pytest.approx(0.025)
        assert sm["sampled_share"] == pytest.approx(40 / 400)
        lo, hi = sm["false_block_wilson95"]
        assert 0.0 < lo < 0.025 < hi  # the CI is real, not decoration
        assert report["verdict"]["within_budget"] is True
        # budget seal binds the report to the registered budget BYTES
        assert report["budget"]["seal_sha256"] == sha256(
            w["budget"].read_bytes()).hexdigest()
        assert "synthetic pilot" in report["pilot_disclosure"]
        out = capsys.readouterr().out
        assert "WITHIN BUDGET" in out
        assert "0.0250" in out

    def test_event_appended_with_seal(self, tmp_path):
        w = _world(tmp_path)
        assert _run(w) == 0
        lines = [json.loads(l) for l in w["decisions"].read_text().splitlines()]
        assert len(lines) == 1
        ev = lines[0]
        assert ev["kind"] == "sm_c1_reported"
        assert ev["payload"]["within_budget"] is True
        assert ev["payload"]["false_block_rate"] == pytest.approx(0.025)
        assert ev["payload"]["shadow_rate_requested"] == pytest.approx(0.10)
        assert ev["payload"]["budget_seal_sha256"] == sha256(
            w["budget"].read_bytes()).hexdigest()

    def test_deterministic_report_for_fixed_now(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        w1 = _world(tmp_path / "a")
        w2 = _world(tmp_path / "b")
        assert _run(w1) == 0
        assert _run(w2) == 0
        assert w1["report"].read_text() == w2["report"].read_text()

    def test_over_budget_pilot_is_flagged(self, tmp_path, capsys):
        w = _world(tmp_path)
        # same pilot, tighter budget -> honest OVER verdict
        w["budget"].write_text(BUDGET_TOML.replace("0.05", "0.01"))
        assert _run(w) == 0
        report = json.loads(w["report"].read_text())
        assert report["verdict"]["within_budget"] is False
        assert "OVER" in report["verdict"]["reason"]
        assert "NOT WITHIN BUDGET" in capsys.readouterr().out


class TestPoisonTolerance:
    def test_torn_and_rejected_lines_counted_not_fatal(self, tmp_path):
        w = _world(tmp_path)
        poisoned = tmp_path / "samples.jsonl"
        good = FIXTURE.read_text().splitlines()[:5]
        poisoned.write_text("\n".join(
            good + ['{"torn',
                    json.dumps({"patch_sha256": "z", "certificate_hash": "a" * 64,
                                "realized_outcome": "valid_execution"}),
                    json.dumps({"patch_sha256": "a" * 64}),
                    json.dumps({"patch_sha256": "b" * 64, "certificate_hash": "c" * 64,
                                "realized_outcome": "judge_verdict"})]) + "\n")
        assert _run(w, samples=poisoned, n_blocks=50) == 0
        report = json.loads(w["report"].read_text())
        st = report["input_stats"]
        assert st["torn_lines"] == 1
        assert st["rejected_rows"] == 3
        assert report["sm_c1"]["n_sampled"] == 5

    def test_empty_shadow_reports_undefined_honestly(self, tmp_path):
        w = _world(tmp_path)
        empty = tmp_path / "empty.jsonl"
        empty.write_text('{"torn\n')
        assert _run(w, samples=empty) == 0
        report = json.loads(w["report"].read_text())
        assert report["sm_c1"]["false_block_rate"] is None
        assert report["verdict"]["within_budget"] is False
        assert "undefined" in report["verdict"]["reason"].lower()


class TestFailClosedInputs:
    def test_missing_samples(self, tmp_path):
        w = _world(tmp_path)
        assert _run(w, samples=tmp_path / "nope.jsonl") == 3

    def test_negative_denominator(self, tmp_path):
        w = _world(tmp_path)
        assert _run(w, n_blocks=-1) == 3

    def test_naive_now_rejected(self, tmp_path):
        w = _world(tmp_path)
        assert _run(w, now="2026-08-15T12:00:00") == 3
