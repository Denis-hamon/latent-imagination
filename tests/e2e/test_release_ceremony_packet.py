"""Ceremony generalization (story 4.4 Task 2): the corpus packet goes down the
SAME chain path on a local fixture — offline (anchor forced to its simulated
fallback, no network), probe call-shape compatibility asserted."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "prereg"))

import release_ceremony as rc


def _force_offline_anchor(monkeypatch):
    """Force the offline branch of anchor_chain without touching the network."""
    import types

    import ots_anchor.anchor as real

    def _boom(chain_hash: str, proof_path: str):
        raise real.AnchorUnavailableError("calendars unreachable (fixture)")

    fake = types.SimpleNamespace(anchor=_boom,
                                 anchor_offline_simulated=real.anchor_offline_simulated)
    monkeypatch.setitem(sys.modules, "ots_anchor.anchor", fake)


def test_corpus_packet_full_chain(tmp_path, monkeypatch):
    _force_offline_anchor(monkeypatch)
    repo = Path(__file__).resolve().parents[2]
    packet = tmp_path / "corpus-packet"
    packet.mkdir()
    (packet / "corpus-release.json").write_text('{"corpus_version": "corpus-v0"}')
    store = tmp_path / "rs"

    arts = rc.build_release_artifacts(repo, store, packet=packet, release_id="corpus-release-2026-08-06")
    assert arts["release_id"] == "corpus-release-2026-08-06"
    payload = rc.anchor_chain(repo, arts, store)  # real repo for ruleset pin + git head
    assert payload["anchor_mode"].startswith("ots-simulated")  # disclosed, offline
    assert payload["chain"]["release"] == arts["release_hash"]
    assert list((store / "chains").glob("*.json"))


def test_probe_call_shape_unchanged(tmp_path, monkeypatch):
    """Old invocation (`<workdir> <store>`, no flags) keeps its exact defaults."""
    _force_offline_anchor(monkeypatch)
    repo = Path(__file__).resolve().parents[2]
    store = tmp_path / "rs"
    arts = rc.build_release_artifacts(repo, store)  # no kwargs — the probe call shape
    assert arts["release_id"] == "probe-measurement-2026-08-05"
    import tarfile

    with tarfile.open(arts["tarball"]) as tar:
        assert tar.getnames()[0] == "probe-design"


def test_release_id_slug_enforced(tmp_path):
    packet = tmp_path / "p"
    packet.mkdir()
    (packet / "x").write_text("y")
    with pytest.raises(SystemExit):
        rc.build_release_artifacts(tmp_path, tmp_path / "rs", packet=packet, release_id="../escape")


def test_act2_packet_rides_the_same_ceremony(tmp_path, monkeypatch):
    """Story 6.4's assembly, but THROUGH the ceremony (offline anchor) — the
    theater leg closed: the packet really goes down the chain."""
    _force_offline_anchor(monkeypatch)
    repo = Path(__file__).resolve().parents[2]
    import json as _json
    from hashlib import sha256 as _sha

    delta = {"claim_line": {"erbve_delta_pp": 25.1, "exec_per_task_delta": -0.2,
                            "time_to_valid_delta_s": None, "ttv_coverage": "0/2",
                            "aggregation": "x", "delta_ci": None, "ci_status": "x"},
             "per_series": [], "tolerance_pp": 2.0,
             "_citations": {"decision_toml_sha256": "e" * 64, "design_toml_sha256": "f" * 64},
             "oq4": {"met": True, "verdict": "material-reduction", "minimum_publishable_pp": 5.0}}
    delta_bytes = (_json.dumps(delta, indent=1, sort_keys=True) + "\n").encode()
    d = tmp_path / "delta.json"
    d.write_bytes(delta_bytes)
    rerun = {"rerun": {"operator": "X", "affiliation": "y"}, "published_delta_pp": 25.1,
             "reproduced_delta_pp": 25.09, "within_tolerance": True,
             "bitwise_anchor": {"expected_sha256": _sha(delta_bytes).hexdigest(), "bitwise_equal": True}}
    r = tmp_path / "rerun.json"
    r.write_text(_json.dumps(rerun))
    pins = tmp_path / "pins.json"
    pins.write_text('{"campaign": "act2"}')

    from publication.act2 import assemble_act2_release

    packet = tmp_path / "act2-packet"
    assemble_act2_release(packet, delta_json=d, rerun_report_json=r,
                          templates_dir=repo / "governance" / "act2" / "verdict-templates",
                          campaign_pins_json=pins, act1_release_hash="a" * 64, code_commit="c" * 64)
    arts = rc.build_release_artifacts(repo, tmp_path / "rs", packet=packet,
                                      release_id="act2-intervention-2026-08-06")
    payload = rc.anchor_chain(repo, arts, tmp_path / "rs")
    assert payload["chain"]["release"] == arts["release_hash"]
    import tarfile

    with tarfile.open(arts["tarball"]) as tar:
        names = tar.getnames()
    assert any(n.endswith("release-manifest-block.json") for n in names)
    assert any(n.endswith("verdict.md") for n in names)


def test_distribute_external_skips_disclosed_without_tokens(monkeypatch):
    """Story 2.6 task 4 close: absent tokens → recorded SKIP, not silence."""
    monkeypatch.delenv("LI_ZENODO_TOKEN", raising=False)
    monkeypatch.delenv("LI_HF_TOKEN", raising=False)
    arts = {"release_id": "x", "tarball": Path("/tmp/none.tar.gz")}
    out = rc.distribute_external(Path("/tmp"), arts, {}, env={})
    assert out["zenodo"].startswith("SKIP")
    assert out["hf_hub"].startswith("SKIP")


def test_distribute_external_zenodo_flow_offline(tmp_path, monkeypatch):
    """Zenodo path through a MockTransport client — full create/upload/publish."""
    import httpx as _hx

    def handler(request):
        if request.method == "POST" and "deposit/depositions" in request.url.path:
            if "publish" in request.url.path:
                return _hx.Response(202, json={"metadata": {"doi": "10.5281/zenodo.9"},
                                               "links": {}})
            return _hx.Response(201, json={"id": 9, "links": {"bucket": "https://f/b"}})
        if request.method == "PUT":
            return _hx.Response(201, json={})
        return _hx.Response(404)

    tarball = tmp_path / "rel.tar.gz"
    tarball.write_bytes(b"PAR1")
    client = _hx.Client(transport=_hx.MockTransport(handler))
    arts = {"release_id": "r", "tarball": tarball}
    out = rc.distribute_external(Path("/tmp"), arts, {},
                                 env={"LI_ZENODO_TOKEN": "t"}, client=client)
    assert out["zenodo"] == "doi:10.5281/zenodo.9"
    assert out["hf_hub"].startswith("SKIP")
