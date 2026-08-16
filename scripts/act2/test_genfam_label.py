"""Story 10.2 — table de décision du classifieur genfam (y-rule s12 + rules-v1).

Chaque cas est un invariant exact (leçon epic-7 retro : pas d'assertions lâches).
Hermétique : pas de docker, pas de réseau — dicts de run-result synthétiques.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "labeling" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "core-schema" / "src"))

_SPEC = importlib.util.spec_from_file_location(
    "genfam_label_build", Path(__file__).resolve().parent / "genfam_label_build.py")
lb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lb)


def _rr(**kw):
    base = {"slot": "acme__repo.deadbeef.func_x__s-d1", "task": "acme__repo.deadbeef.func_x__s",
            "bug_applied": True, "patch_applied": True,
            "f2p_rc": 0, "f2p_tail": "2 passed in 0.05s\n"}
    base.update(kw)
    return base


def test_f2p_vert_p2p_nondeclares_y1():
    lbl, q, y = lb.classify_slot(_rr(p2p_rc=None), "e")
    assert q is None and y == 1 and lbl["outcome"] == "valid_execution"


def test_f2p_vert_p2p_verts_y1():
    lbl, _q, y = lb.classify_slot(_rr(p2p_rc=0, p2p_tail="20 passed"), "e")
    assert y == 1 and lbl["outcome"] == "valid_execution"


def test_f2p_vert_p2p_rouge_est_un_veto_y0():
    lbl, _q, y = lb.classify_slot(_rr(p2p_rc=1, p2p_tail="2 failed, 18 passed"), "e")
    assert y == 0 and lbl["outcome"] == "false_start_tests_ran_no_flip"


def test_f2p_rouge_y0():
    lbl, _q, y = lb.classify_slot(_rr(f2p_rc=1, f2p_tail="1 failed, error: assert"), "e")
    assert y == 0 and lbl["outcome"] == "false_start_tests_ran_no_flip"


def test_f2p_rouge_infra_label_infrastructure():
    lbl, _q, y = lb.classify_slot(
        _rr(f2p_rc=1, f2p_tail="Segmentation fault\n(core dumped)"), "e")
    assert y == 0 and lbl["outcome"] == "false_start_infrastructure_failure"


def test_patch_inapplicable_quarantaine_env():
    lbl, q, y = lb.classify_slot(_rr(patch_applied=False, apply_err="…"), "e")
    assert lbl is None and y is None and q["reason_code"] == "environment_undetermined"


def test_erreur_docker_quarantaine_env():
    lbl, q, _y = lb.classify_slot(_rr(error="docker run failed"), "e")
    assert lbl is None and q["reason_code"] == "environment_undetermined"


def test_sortie_ambigue_quarantaine_amb():
    # timeout sans excuse "0 timeouts" → rules_v1 None → quarantine
    lbl, q, _y = lb.classify_slot(_rr(f2p_rc=1, f2p_tail="test timed out\nkilled"), "e")
    assert lbl is None and q["reason_code"] == "ambiguous_output"


def test_f2p_verts_mais_chaine_p2p_interrompue_quarantaine():
    # p2p déclarés côté staging mais absents du run-result = interruption ≠ absence
    lbl, q, _y = lb.classify_slot(_rr(), "e")  # pas de clé p2p_rc du tout
    assert lbl is None and q["reason_code"] == "environment_undetermined"


def test_cap_quarantaine_refuse_emission(tmp_path):
    # 10 mesurables + 2 quarantaines = 16.7 % > 10 % → build refuse (rc=2),
    # n'émet PAS labels-rules-v1.json, et journalise le refus
    import json
    qdir = tmp_path / "genfam-q1"
    res = qdir / "gen-results"
    for i in range(10):
        d = res / f"t{i:02d}__r.aa.func__s-d1"
        d.mkdir(parents=True)
        (d / "run-result.json").write_text(json.dumps(
            {"slot": d.name, "task": f"t{i:02d}__r.aa.func__s", "bug_applied": True,
             "patch_applied": True, "f2p_rc": 0, "f2p_tail": "1 passed",
             "p2p_rc": None, "campaign": "genfam-q1", "window": "gen-families-v1"}))
    for i in range(2):
        d = res / f"bad{i}__r.bb.func__s-d1"
        d.mkdir(parents=True)
        (d / "run-result.json").write_text(json.dumps(
            {"slot": d.name, "task": f"bad{i}__r.bb.func__s",
             "bug_applied": True, "patch_applied": False,
             "f2p_tail": ""}))
    rc, rep = lb.build(qdir)
    assert rc == 2 and rep["status"] == "REFUSED"
    assert rep["quarantines"] == 2 and rep["labels"] == 10
    assert not (qdir / "labels" / "labels-rules-v1.json").exists()  # rien d'émis
    refused = json.loads((qdir / "labels" / "genfam-label-report.json").read_text())
    assert refused["status"] == "REFUSED"


def test_emission_normale_cite_ruleset(tmp_path):
    import json
    qdir = tmp_path / "genfam-q1"
    d = qdir / "gen-results" / "ok__r.aa.func__s-d1"
    d.mkdir(parents=True)
    (d / "run-result.json").write_text(json.dumps(
        {"slot": "ok__r.aa.func__s-d1", "task": "ok__r.aa.func__s",
         "bug_applied": True, "patch_applied": True, "f2p_rc": 0,
         "f2p_tail": "1 passed", "p2p_rc": None,
         "campaign": "genfam-q1", "window": "gen-families-v1"}))
    rc, rep = lb.build(qdir)
    assert rc == 0 and rep["y1"] == 1 and rep["quarantine_share"] == 0.0
    labels = json.loads((qdir / "labels" / "labels-rules-v1.json").read_text())
    assert labels[0]["ruleset_version"] == lb.RULESET_VERSION  # cite rules-v1 (FR-3)
    assert labels[0]["outcome"] == "valid_execution"
