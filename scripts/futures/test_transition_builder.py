"""v43 — non-régression transition_builder : isolation par fenêtre."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "tb", ROOT / "scripts" / "futures" / "transition_builder.py")
tb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tb)


def _row(cid, issue, model, turn, failed, applied=True):
    return {"id": cid, "issue": issue, "model": model, "turn": turn,
            "applied": applied, "failed_all": failed, "y": 0 if failed else 1}


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    nh = tmp_path / "night-harvest"
    nh.mkdir()
    (tmp_path / "mswb").mkdir()
    monkeypatch.setattr(tb, "NH", nh)
    monkeypatch.setattr(tb, "MSWB", tmp_path / "mswb")
    monkeypatch.setattr(tb, "OUT", tmp_path / "out")
    return nh


def test_isolation_fenetres_meme_issue_meme_modele(sandbox, tmp_path, monkeypatch):
    issue = "repoA-tests_unit_ticket-1"
    model = "DeepSeek-V4-Pro"
    dec = ["t one", "t two", "t three"]
    (sandbox / "replay-v32").mkdir()
    (sandbox / "replay-v32" / "replay-selection-v32.json").write_text(
        json.dumps({"tickets": [{"issue": issue, "f2p": dec}]}) + "\n")
    for w in ("v32", "v35"):
        (sandbox / "replay-v33.jsonl") if False else None
        (sandbox / f"replay-rows-{w}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in [
                _row(f"{w}-t1", issue, model, 1, ["t one", "t two"]),
                _row(f"{w}-t2", issue, model, 2, ["t one"]),
            ]) + "\n")
        d = sandbox / f"replay-{w}" / "repoA-tests_unit_ticket-1--pro"
        d.mkdir(parents=True)
        (d / "t1.diff").write_text("diff --git a/x b/x\n")
        (d / "t2.diff").write_text("diff --git a/x b/x\n")
    monkeypatch.setattr(tb, "WINDOWS", ("v32", "v35"))
    rc = tb.main()
    assert rc == 0
    out = tmp_path / "out" / "v39-transitions.jsonl"
    trans = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    # 1 transition par fenêtre — JAMAIS de transition v32 t2 -> v35 t1
    assert len(trans) == 2
    keys = {t["key"] for t in trans}
    assert keys == {f"v32-{issue}-pro-1>2", f"v35-{issue}-pro-1>2"}
    assert all(t["window"] in ("v32", "v35") for t in trans)


def test_fenetre_sans_tours_consecutifs_ne_produit_rien(sandbox, tmp_path, monkeypatch):
    issue = "repoB-tests_unit_ticket-2"
    model = "DeepSeek-V4-Pro"
    dec = ["a", "b"]
    (sandbox / "replay-rows-v32.jsonl").write_text(
        "\n".join(json.dumps(r) for r in [
            _row("v32-t1", issue, model, 1, ["a"]),
            _row("v32-t2", issue, model, 2, [], applied=False),
            _row("v32-t3", issue, model, 3, ["b"]),
        ]) + "\n")
    d = sandbox / "replay-v32" / "repoB-tests_unit_ticket-2--pro"
    d.mkdir(parents=True)
    (d / "t1.diff").write_text("diff\n")
    (d / "t3.diff").write_text("diff\n")
    (sandbox / "replay-v32").joinpath("replay-selection-v32.json").write_text(
        json.dumps({"tickets": [{"issue": issue, "f2p": dec}]}) + "\n")
    monkeypatch.setattr(tb, "WINDOWS", ("v32",))
    tb.main()
    out = tmp_path / "out" / "v39-transitions.jsonl"
    trans = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    # t1 -> t3 ne sont pas consécutifs : aucune transition
    assert trans == []
