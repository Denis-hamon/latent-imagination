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

    def test_flywheel_colon_rows_share_one_family(self):
        # cohérence Mondrian 12.2 : la calibration stratifie flywheel:* sous
        # la famille « flywheel » ; family_of doit produire le même préfixe
        assert gs.family_of("flywheel:17cd6931f51276d9") == "flywheel"
        assert gs.family_of("flywheel:a69afccacf0e7a33") == "flywheel"

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


class TestConformalTau:
    """Story 12.2 : choix de seuil conforme servi (fonction pure — ni pool,
    ni embed, ni réseau). Mondrian si la strate a une garantie, repli pooled
    HONNÊTE sinon (jamais de garantie par famille fabriquée, FR-27)."""

    CAL = {
        "strata_mondrian": {
            "acme__big": {"alpha_0.10": {"tau": 0.2, "n": 40, "guarantee": "≤0.1 stratum",
                                          "realized_err_rate": 0.05}},
            "thin__fam": {"alpha_0.10": {"tau": None, "n": 4,
                                          "reason": "insufficient data (n=4 < 12)"}},
        },
        "global_conformal": {"alpha_0.10": {"tau": 0.12, "guarantee": "≤0.1 pool",
                                             "realized_err_rate": 0.079}},
    }

    def test_family_stratum_with_guarantee_uses_mondrian(self):
        r = gs.conformal_tau(self.CAL, "acme__big")
        assert r["tau"] == 0.2 and r["source"] == "mondrian-family"
        assert r["guarantee"] == "≤0.1 stratum"

    def test_insufficient_stratum_falls_back_to_pooled_with_disclosure(self):
        r = gs.conformal_tau(self.CAL, "thin__fam")
        assert r["tau"] == 0.12 and r["source"].startswith("global-pooled")
        assert "insuffisant" in r["source"]  # la disclosure porte l'honnêteté

    def test_unknown_family_falls_back_to_pooled(self):
        r = gs.conformal_tau(self.CAL, "jamais__vue")
        assert r["tau"] == 0.12 and r["source"].startswith("global-pooled")

    def test_no_guarantee_anywhere_means_no_tau(self):
        assert gs.conformal_tau({}, "x") == {}  # abstention reste le défaut

    def test_inf_tau_stratum_not_served(self):
        cal = {"strata_mondrian": {"bad__fam": {"alpha_0.10":
                 {"tau": float("inf"), "n": 30, "guarantee": "abstention totale"}}},
               "global_conformal": {"alpha_0.10": {"tau": 0.12}}}
        r = gs.conformal_tau(cal, "bad__fam")
        assert r["tau"] == 0.12  # inf = strate abstention totale ⇒ repli pooled


CONFORMAL_FILE = (Path(__file__).resolve().parents[2] / "governance" / "act2"
                  / "arm-artifacts" / "risk-scan-v10-conformal.json")


class TestTsFlavor:
    """Story 14.4 issue B : détection TS/monorepo conservative (fonction pure)."""

    def test_ts_extensions(self):
        assert gs.ts_flavor("x", "diff --git a/apps/front/page.tsx b/apps/front/page.tsx")
        assert gs.ts_flavor("import { x } from './mod.cts'", "")

    def test_react_next_markers(self):
        assert gs.ts_flavor('from "react"', "")
        assert gs.ts_flavor("config next/route", "")

    def test_python_not_flagged(self):
        assert not gs.ts_flavor("def foo():\n    return 1", "diff --git a/src/x.py b/src/x.py")


@NEEDS_POOL
class TestRiskScanConformalServing:
    """12.2 integration : risk_scan sert l'abstention conforme + disclosures
    (régime nommé, calibration auditée, truncation) quand LI_CONFORMAL_CALIB
    est posée ; rollback trivial = variable absente → régime tau-fixe."""

    ARGS = {"state_text": "fixture state", "diff_text": "diff --git a/x b/x\n+1\n"}

    @pytest.fixture()
    def conformal_server(self, offline_server, monkeypatch):
        if not CONFORMAL_FILE.is_file():
            pytest.skip("artefact conforme 12.1 absent")
        monkeypatch.setattr(gs, "CONFORMAL_CALIB", CONFORMAL_FILE)
        monkeypatch.setattr(gs, "_conformal_cache", None)
        return offline_server

    def test_response_names_regime_and_disclosures(self, conformal_server):
        out = gs.do_risk_scan(dict(self.ARGS, reporter="pytest-fixture"))
        assert out["served_regime"] in ("conformal-mondrian", "fixed-tau")
        assert "calibration_served" in out
        assert any("advisory only" in d for d in out["disclosures"])
        if out["served_regime"] == "conformal-mondrian":
            assert "conformal" in out  # strate + garantie publiées au client
            assert "guarantee" in out["conformal"]

    def test_long_diff_truncation_is_disclosed(self, conformal_server):
        big = dict(self.ARGS, diff_text="diff --git a/x b/x\n" + ("+line\n" * 900),
                   reporter="pytest-fixture")
        out = gs.do_risk_scan(big)
        assert any("3000" in d for d in out["disclosures"])

    def test_ts_query_abstains_with_named_non_coverage(self, offline_server, monkeypatch):
        # requête au signal TS qui s'abstient ⇒ named_non_coverage (issue B),
        # le pool v10 n'ayant aucune strate TS (coverage-ts-1 archivée)
        def sparse_embed(text):
            v = np.zeros(768, dtype=np.float32)
            v[hash(text) % 768] = 1.0
            return v
        monkeypatch.setattr(gs, "embed", sparse_embed)
        out = gs.do_risk_scan({"state_text": "Next.js app",
                               "diff_text": "diff --git a/apps/front/page.tsx b/apps/front/page.tsx\n+1\n",
                               "reporter": "pytest-fixture"})
        if out.get("abstain"):
            assert "named_non_coverage" in out
            assert "TS/monorepo" in out["named_non_coverage"]

    def test_response_discloses_encoder(self, offline_server, monkeypatch):
        # v0.6.0 : la réponse nomme l'encodeur de l'espace géométrique servi
        monkeypatch.setattr(gs, "ENCODER", "jinaai/jina-embeddings-v2-base-code")
        out = gs.do_risk_scan(dict(self.ARGS, reporter="pytest-fixture"))
        assert out["encoder"] == "jinaai/jina-embeddings-v2-base-code"

    def test_embedder_family_dispatch(self):
        assert gs._embedder_family("jinaai/jina-embeddings-v2-base-code") == "jina"
        assert gs._embedder_family("microsoft/unixcoder-base") == "unixcoder"

    def test_no_conformal_env_means_legacy_tau_regime(self, offline_server, monkeypatch):
        monkeypatch.setattr(gs, "CONFORMAL_CALIB", Path(""))
        monkeypatch.setattr(gs, "_conformal_cache", None)
        out = gs.do_risk_scan(dict(self.ARGS, reporter="pytest-fixture"))
        assert out["served_regime"] == "fixed-tau"
        assert "conformal" not in out
