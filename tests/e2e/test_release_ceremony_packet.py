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
