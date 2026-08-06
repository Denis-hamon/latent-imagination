"""Gate interface + read port (story 5.1) — pinned snapshot only, advisory by
construction, disclosure mandatory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from core_schema.events import StoreEvent
from gate.decision_log import append_decision
from gate.intercept import annotate, timed
from gate.ports import INTERFACE_VERSION, load_pinned_snapshot

DISCLOSURE = {"measured_precision": 0.6271, "posture": "sub-bar advisory (branch iii)"}


def _snapshot(tmp_path, *, pred_ver="probe-predictor-v0", corpus="corpus-v0"):
    (tmp_path / "META.json").write_text(json.dumps(
        {"layout_version": "store-layout-v1", "store_version": "a" * 64}))
    (tmp_path / "predictor.json").write_text(json.dumps({
        "predictor_version": pred_ver, "corpus_version": corpus,
        "measured": {"precision": 0.6271}}))
    return tmp_path


class TestReadPort:
    def test_load_ok(self, tmp_path):
        snap = load_pinned_snapshot(_snapshot(tmp_path))
        assert snap.predictor_version == "probe-predictor-v0"
        assert snap.corpus_version == "corpus-v0"
        assert INTERFACE_VERSION == "gate-iface-v1"

    def test_hash_pin_enforced(self, tmp_path):
        root = _snapshot(tmp_path)
        snap = load_pinned_snapshot(root)
        ok = load_pinned_snapshot(root, expected_predictor_hash=snap.predictor_hash)
        assert ok.predictor_hash == snap.predictor_hash
        with pytest.raises(SchemaError) as ei:
            load_pinned_snapshot(root, expected_predictor_hash="0" * 64)
        assert ei.value.code == "LI-GATE-001"

    def test_unsupported_predictor_version_refused(self, tmp_path):
        with pytest.raises(SchemaError):
            load_pinned_snapshot(_snapshot(tmp_path, pred_ver="probe-predictor-v99"))

    def test_missing_store_version_refused(self, tmp_path):
        (tmp_path / "META.json").write_text("{}")
        (tmp_path / "predictor.json").write_text('{"predictor_version": "probe-predictor-v0"}')
        with pytest.raises(SchemaError):
            load_pinned_snapshot(tmp_path)


class TestAnnotate:
    def test_event_is_trace_schema(self, tmp_path):
        snap = load_pinned_snapshot(_snapshot(tmp_path))
        ev, lat = timed(annotate, snap, flip_probability=0.62, model_family="baseline",
                        latency_s=0.001, disclosure=DISCLOSURE)
        assert isinstance(ev, StoreEvent)
        assert ev.kind == "gate_annotated"
        assert ev.occurred_at.tzinfo is not None
        assert lat >= 0
        p = ev.payload
        assert p["interface_version"] == "gate-iface-v1"
        assert p["predictor_hash"] == snap.predictor_hash
        assert p["predictor_disclosure"]["measured_precision"] == 0.6271

    def test_no_disclosure_no_annotation(self, tmp_path):
        snap = load_pinned_snapshot(_snapshot(tmp_path))
        with pytest.raises(SchemaError):
            annotate(snap, flip_probability=0.5, model_family="x", latency_s=0.0, disclosure={})

    def test_probability_bounds(self, tmp_path):
        snap = load_pinned_snapshot(_snapshot(tmp_path))
        with pytest.raises(SchemaError):
            annotate(snap, flip_probability=1.5, model_family="x", latency_s=0.0, disclosure=DISCLOSURE)

    def test_no_blocking_surface_exists(self):
        """FR-19 by construction: greppable absence."""
        import gate.intercept as gi

        src = Path(gi.__file__).read_text()
        for banned in ("block", "halt", "deny"):
            assert f"def {banned}" not in src
            assert f'"{banned}":' not in src


class TestDecisionLog:
    def test_append_only_jsonl(self, tmp_path):
        snap = load_pinned_snapshot(_snapshot(tmp_path))
        ev = annotate(snap, flip_probability=0.5, model_family="x", latency_s=0.0, disclosure=DISCLOSURE)
        log = tmp_path / "store" / "decisions.jsonl"
        append_decision(log, ev)
        append_decision(log, ev)
        lines = log.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["kind"] == "gate_annotated"

    def test_wrong_filename_refused(self, tmp_path):
        snap = load_pinned_snapshot(_snapshot(tmp_path))
        ev = annotate(snap, flip_probability=0.5, model_family="x", latency_s=0.0, disclosure=DISCLOSURE)
        with pytest.raises(SchemaError):
            append_decision(tmp_path / "other.jsonl", ev)
