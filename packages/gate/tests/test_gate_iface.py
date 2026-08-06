"""Gate interface + read port (story 5.1 + CR) — pinned snapshot only, advisory
by construction, disclosure validated, abstention a first-class event."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from core_schema.events import StoreEvent
from gate.decision_log import append_decision
from gate.intercept import CandidateCtx, annotate, refuse
from gate.ports import INTERFACE_VERSION, load_pinned_snapshot

DISCLOSURE = {"measured_precision": 0.6271, "posture": "sub-bar advisory (branch iii)"}
CTX = CandidateCtx(repo="o/r", patch_diff="diff --git a/x b/x\n+1\n",
                   rationale_ptr="governance/probe-design/model-strategy-v1.md")


def _snapshot(tmp_path, *, pred_ver="probe-predictor-v0", corpus="corpus-v0",
              layout="store-layout-v1", store_version="a" * 64):
    (tmp_path / "META.json").write_text(json.dumps(
        {"layout_version": layout, "store_version": store_version}))
    pred = {"predictor_version": pred_ver, "corpus_version": corpus,
            "measured": {"precision": 0.6271}}
    (tmp_path / "predictor.json").write_text(json.dumps(pred))
    return tmp_path, sha256(json.dumps(pred).encode()).hexdigest()


def _snap_kwargs(tmp_path, **kw):
    root, phash = _snapshot(tmp_path, **kw)
    return root, phash


def _annotate(tmp_path):
    root, phash = _snap_kwargs(tmp_path)
    snap = load_pinned_snapshot(root, expected_predictor_hash=phash)
    return annotate(snap, CTX, flip_probability=0.62, model_family="baseline",
                    latency_s=0.001, disclosure=DISCLOSURE,
                    prediction_target_tier="diff_touched")


class TestReadPort:
    def test_load_ok(self, tmp_path):
        root, phash = _snap_kwargs(tmp_path)
        snap = load_pinned_snapshot(root, expected_predictor_hash=phash)
        assert snap.predictor_version == "probe-predictor-v0"
        assert snap.corpus_version == "corpus-v0"
        assert INTERFACE_VERSION == "gate-iface-v1"

    def test_pin_is_mandatory_and_enforced(self, tmp_path):
        root, _ = _snap_kwargs(tmp_path)
        with pytest.raises(SchemaError):  # wrong pin
            load_pinned_snapshot(root, expected_predictor_hash="0" * 64)
        with pytest.raises(SchemaError):  # non-hex pin
            load_pinned_snapshot(root, expected_predictor_hash="zzz")

    def test_missing_manifests_fail_closed(self, tmp_path):
        with pytest.raises(SchemaError) as ei:
            load_pinned_snapshot(tmp_path, expected_predictor_hash="0" * 64)
        assert ei.value.code == "LI-GATE-001"


    def test_non_dict_manifest_fails_closed(self, tmp_path):
        (tmp_path / "META.json").write_text("[1,2,3]")
        (tmp_path / "predictor.json").write_text("{}")
        with pytest.raises(SchemaError):
            load_pinned_snapshot(tmp_path, expected_predictor_hash="0" * 64)

    def test_layout_and_store_version_validated(self, tmp_path):
        root, phash = _snap_kwargs(tmp_path, layout="store-layout-v99")
        with pytest.raises(SchemaError):
            load_pinned_snapshot(root, expected_predictor_hash=phash)
        b = tmp_path / "b"
        b.mkdir()
        root2, phash2 = _snapshot(b, store_version="z" * 64)  # 64 chars but not hex
        with pytest.raises(SchemaError):
            load_pinned_snapshot(root2, expected_predictor_hash=phash2)

    def test_unsupported_predictor_and_corpus_fail(self, tmp_path):
        root, phash = _snap_kwargs(tmp_path, pred_ver="v99")
        with pytest.raises(SchemaError):
            load_pinned_snapshot(root, expected_predictor_hash=phash)
        root, phash = _snap_kwargs(tmp_path, corpus="garbage")
        with pytest.raises(SchemaError):
            load_pinned_snapshot(root, expected_predictor_hash=phash)


class TestAnnotate:
    def test_event_shape(self, tmp_path):
        ev = _annotate(tmp_path)
        assert ev.kind == "gate_annotated"
        p = ev.payload
        assert p["candidate"]["repo"] == "o/r"
        assert p["candidate"]["patch_sha256"] == sha256(CTX.patch_diff.encode()).hexdigest()
        assert p["rationale_ptr"].endswith("model-strategy-v1.md")
        assert p["prediction_target_tier"] == "diff_touched"

    def test_disclosure_must_match_the_pin(self, tmp_path):
        root, phash = _snap_kwargs(tmp_path)
        snap = load_pinned_snapshot(root, expected_predictor_hash=phash)
        bad = {"measured_precision": 0.99, "posture": "fabricated"}
        with pytest.raises(SchemaError):
            annotate(snap, CTX, flip_probability=0.5, model_family="x",
                     latency_s=0.0, disclosure=bad, prediction_target_tier="diff_touched")

    def test_numeric_guards(self, tmp_path):
        root, phash = _snap_kwargs(tmp_path)
        snap = load_pinned_snapshot(root, expected_predictor_hash=phash)
        for bad in (1.5, float("nan"), float("inf"), "0.5", True):
            with pytest.raises(SchemaError):
                annotate(snap, CTX, flip_probability=bad, model_family="x",
                         latency_s=0.0, disclosure=DISCLOSURE, prediction_target_tier="diff_touched")
        with pytest.raises(SchemaError):
            annotate(snap, CTX, flip_probability=0.5, model_family="x",
                     latency_s=-1.0, disclosure=DISCLOSURE, prediction_target_tier="diff_touched")

    def test_abstention_is_first_class(self, tmp_path):
        root, phash = _snap_kwargs(tmp_path)
        snap = load_pinned_snapshot(root, expected_predictor_hash=phash)
        ev = refuse(snap, CTX, reason="no F2P denominator (OQ-10 abstain)")
        assert ev.kind == "prediction_refused"
        assert "flip_probability" not in ev.payload


class TestDecisionLog:
    def test_append_utf8_and_kind_guard(self, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        ev = _annotate(work)  # snapshot under work/snap, decision log OUTSIDE it
        log = tmp_path / "deployer-local" / "decisions.jsonl"
        append_decision(log, ev)
        append_decision(log, ev)
        assert len(log.read_text(encoding="utf-8").strip().splitlines()) == 2
        foreign = StoreEvent(schema_version=1, kind="attempt_labeled",
                             occurred_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                             payload={})
        with pytest.raises(SchemaError):
            append_decision(log, foreign)

    def test_refuses_to_write_inside_a_store_root(self, tmp_path):
        """AD-4 fence, constructed: a store root (META.json at an ancestor) is off-limits."""
        store = tmp_path / "canonical-store"
        store.mkdir()
        (store / "META.json").write_text("{}")
        work = tmp_path / "work"
        work.mkdir()
        ev = _annotate(work)
        with pytest.raises(SchemaError) as ei:
            append_decision(store / "decisions.jsonl", ev)
        assert ei.value.code == "LI-GATE-004"

    def test_write_errors_are_coded(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        work = tmp_path / "work"
        work.mkdir()
        ev = _annotate(work)
        with pytest.raises(SchemaError):
            append_decision(blocker / "decisions.jsonl", ev)  # parent is a file


def test_no_blocking_surface_anywhere_in_the_package():
    """FR-19: scan ALL gate modules for a blocking surface."""
    import gate

    for f in Path(gate.__file__).parent.glob("*.py"):
        src = f.read_text()
        for banned in ("def block", "def halt", "def deny"):
            assert banned not in src, f"{f.name} grew a blocking surface"
