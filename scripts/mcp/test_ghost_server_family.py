"""ghost_server v0.4.0 — family metadata + abstention diagnostics + reporter
signaling. Tested without torch: embed() is monkeypatched to deterministic
vectors; the served pool v8 (numpy) is the real fixture. Decision semantics
(attractor + tau) are asserted UNCHANGED — the family block is additive."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
import ghost_server as gs

# Pool v8 lives in data/landing (gitignored — absent on clean CI runners);
# pool-dependent tests skip like the demo e2e guards, pure logic always runs.
NEEDS_POOL = pytest.mark.skipif(
    not gs.POOL_JSON.is_file(),
    reason=f"served pool {gs.POOL_JSON.name} absent (data/landing, gitignored — node/local only)")


class TestFamilyOf:
    def test_repo_prefix(self):
        assert gs.family_of("pandas-dev__pandas.0b4f4937.func_x__5rijazp0") == "pandas-dev__pandas"
        assert gs.family_of("pyca__pyopenssl.04766a49.combine_file__ia85jsve") == "pyca__pyopenssl"

    def test_no_dot_falls_back_to_task(self):
        assert gs.family_of("bare-task-name") == "bare-task-name"

    def test_non_string_safe(self):
        assert gs.family_of(None) == "None"


@NEEDS_POOL
class TestPoolFamilyWiring:
    def test_real_pool_carries_families(self):
        pc = gs._load_pool()
        assert pc["families"].shape == (pc["n"],)
        assert len(set(pc["families"].tolist())) > 10  # 54 families measured on v8
        for fam in pc["families"]:
            assert "." not in fam  # prefix extraction is total

    def test_family_coverage_counts_match_pool(self):
        pc = gs._load_pool()
        cov = gs._family_coverage(pc)
        assert sum(v["n"] for v in cov.values()) == pc["n"]
        assert sum(v["positives"] for v in cov.values()) == int(pc["y"].sum())

    def test_family_coverage_respects_exclusion(self):
        pc = gs._load_pool()
        keep = np.ones(pc["n"], bool)
        keep[0] = False
        excluded_fam = pc["families"][0]
        cov_ex = gs._family_coverage(pc, exclude=keep.tolist())
        cov_all = gs._family_coverage(pc)
        one_fam = pc["families"] == excluded_fam
        if int(one_fam.sum()) == 1:  # the excluded family had a single row
            assert excluded_fam not in cov_ex
        else:
            assert cov_ex.get(excluded_fam, {}).get("n", 0) == int(one_fam.sum()) - 1
        assert cov_all[excluded_fam]["n"] == int(one_fam.sum())


@NEEDS_POOL
class TestFamilyDiagnosis:
    def test_diagnosis_shape_on_real_pool(self):
        pc = gs._load_pool()
        q = pc["E_s"][0]  # a real pool state embedding, already normalized
        diag = gs._family_diagnosis(q, pc)
        assert diag["nearest_family"] == pc["families"][0]
        assert diag["nearest_similarity"] == pytest.approx(1.0, abs=1e-3)
        cov = diag["family_coverage"]
        assert cov["n"] >= 1 and cov["positives"] + cov["negatives"] == cov["n"]
        assert diag["families_in_pool"] == len(set(pc["families"].tolist()))
        assert diag["pool_n"] == pc["n"]
        assert len(diag["top5_families_by_state"]) == 5


@pytest.fixture()
def offline_server(tmp_path, monkeypatch):
    """risk_scan with a deterministic embed and a tmp log — no torch, no net."""
    pc = gs._load_pool()
    cal = gs._load_risk_calib()
    thr = cal.get("thr_pool")

    def _most_confident_positive():
        # pick the positive row maximizing |f1 - thr| so the served regime fires
        cd, y = pc["cd"], pc["y"]
        sims = cd @ cd.T
        best, best_conf = None, -1.0
        for i in np.where(y == 1)[0]:
            d_pass = float((1 - sims[i][y == 1]).min())
            d_fail = float((1 - sims[i][y == 0]).min())
            conf = abs((d_fail - d_pass) - thr)
            if conf > best_conf:
                best_conf, best = conf, int(i)
        return best

    def fake_embed(text):
        v = pc["cd"][_most_confident_positive()] / 2.0  # q_s+q_d renormalizes to cd[i]
        return v.astype(np.float32)

    monkeypatch.setattr(gs, "embed", fake_embed)
    monkeypatch.setattr(gs, "LOG_PATH", tmp_path / "mcp-log.jsonl")
    return tmp_path


@NEEDS_POOL
class TestRiskScanAdditiveFields:
    ARGS: ClassVar[dict] = {"state_text": "fixture state", "diff_text": "diff --git a/x b/x\n+1\n"}

    def test_decision_path_unchanged_and_family_block_present(self, offline_server, monkeypatch):
        out = gs.do_risk_scan(dict(self.ARGS, reporter="pytest-fixture"))
        # decision regime fields stay the contract
        assert out["decision"] in ("low_risk", "high_risk", "abstain")
        assert "attractor_score" in out and "confidence" in out
        # additive family block
        fam = out["family"]
        assert fam["nearest_family"] in set(gs._load_pool()["families"].tolist())
        assert fam["pool_n"] == gs._load_pool()["n"]
        assert "call_id" in out

    def test_confident_query_yields_verdict_not_abstain(self, offline_server):
        """q == exact pool composite of a positive row: d_pass = 0, conf >= tau
        -> the served recipe must answer low_risk (proves the regime still fires)."""
        out = gs.do_risk_scan(dict(self.ARGS, reporter="pytest-fixture"))
        assert out["decision"] == "low_risk"
        assert out["abstain"] is False

    def test_abstain_carries_diagnosis_when_confidence_low(self, offline_server, monkeypatch):
        def sparse_embed(text):
            v = np.zeros(768, dtype=np.float32)
            v[hash(text) % 768] = 1.0  # far from the pool cloud -> low confidence
            return v

        monkeypatch.setattr(gs, "embed", sparse_embed)
        out = gs.do_risk_scan(dict(self.ARGS, reporter="pytest-fixture"))
        if out["abstain"]:
            assert "abstention_diagnosis" in out
            assert out["family"]["nearest_family"] in out["abstention_diagnosis"]

    def test_missing_reporter_is_signaled_and_logged(self, offline_server):
        out = gs.do_risk_scan(dict(self.ARGS))  # no reporter
        assert "reporter_note" in out
        assert "stratifié par auteur" in out["reporter_note"]
        log = [json.loads(l) for l in (offline_server / "mcp-log.jsonl").read_text().splitlines()]
        assert log[-1]["reporter_missing"] is True
        assert log[-1]["reporter"] == ""
        assert "nearest_family" in log[-1]

    def test_reporter_present_not_flagged(self, offline_server):
        out = gs.do_risk_scan(dict(self.ARGS, reporter="qwen3.8-bmad-epic7"))
        assert "reporter_note" not in out
        log = [json.loads(l) for l in (offline_server / "mcp-log.jsonl").read_text().splitlines()]
        assert log[-1]["reporter_missing"] is False
        assert log[-1]["reporter"] == "qwen3.8-bmad-epic7"


@NEEDS_POOL
class TestBearerVerification:
    """Story #5 hardening: pure token check (constant-time, fail-closed)."""

    def test_valid_bearer(self):
        assert gs.verify_bearer_token("Bearer s3cret-token", "s3cret-token") is True

    def test_case_insensitive_scheme_exact_token(self):
        assert gs.verify_bearer_token("bearer s3cret-token", "s3cret-token") is True
        assert gs.verify_bearer_token("Bearer wrong-token", "s3cret-token") is False

    def test_invalid_shapes_refused(self):
        for bad in (None, "", "s3cret-token", "Basic abc", "Bearer ", "Bearer"):
            assert gs.verify_bearer_token(bad, "s3cret-token") is False

    def test_empty_policy_token_refuses_everything(self):
        assert gs.verify_bearer_token("Bearer anything", "") is False
        assert gs.verify_bearer_token(None, "") is False


class TestNearMisFamily:
    def test_nearest_rows_carry_family(self, tmp_path, monkeypatch):
        pc = gs._load_pool()

        def fake_embed(text):
            return pc["E_s"][0].astype(np.float32)

        monkeypatch.setattr(gs, "embed", fake_embed)
        monkeypatch.setattr(gs, "LOG_PATH", tmp_path / "mcp-log.jsonl")
        out = gs.do_near_mis_patches({"state_text": "s", "diff_text": "d", "goal_text": "g", "k": 3})
        assert len(out["nearest"]) == 3
        for row in out["nearest"]:
            assert row["family"] == gs.family_of(row["task"])
