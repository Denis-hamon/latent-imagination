"""Store contract tests: emit + validate, with function-proving tamper fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from store.emit import (
    WRITERS,
    StoreWriteError,
    compute_store_version,
    write_artifact,
)
from store.layout import EMPTY_STORE_VERSION, LAYOUT_VERSION
from store.validate import validate_store


def _mkfile(d: Path, name: str, content: bytes) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(content)
    return p


def good_inputs() -> dict:
    return {
        "store_snapshot": "a" * 64,
        "ruleset_version": "rules-v1",
        "code_commit": "f" * 40,
        "seeds": {"numpy": 42},
    }


@pytest.fixture()
def store_root(tmp_path: Path) -> Path:
    return tmp_path / "store"


class TestEmit:
    def test_happy_path_manifest_and_meta(self, store_root):
        f = _mkfile(store_root.parent / "w", "snap.parquet", b"PAR1fake")
        art = write_artifact(
            stage="traces-ingest",
            artifact_type="canonical-snapshot",
            artifact_id="snap-001",
            artifact_version="v0",
            files=[f],
            inputs=good_inputs(),
            store_root=store_root,
        )
        man = json.loads(art.manifest_path.read_text())
        assert man["layout_version"] == LAYOUT_VERSION
        assert man["producer"] == "traces-ingest"
        assert man["artifact_class"] == "reproducible"
        assert "created_at" not in man  # AD-7 hygiene
        assert man["inputs"] == good_inputs()
        assert man["files"][0]["sha256"]
        meta = json.loads((store_root / "META.json").read_text())
        assert meta["store_version"] == compute_store_version(store_root)

    def test_rewrite_same_content_is_noop(self, store_root):
        f = _mkfile(store_root.parent / "w", "snap.parquet", b"PAR1a")
        a = write_artifact("traces-ingest", "canonical-snapshot", "snap-001", "v0", [f], good_inputs(), store_root)
        b = write_artifact("traces-ingest", "canonical-snapshot", "snap-001", "v0", [f], good_inputs(), store_root)
        assert a.manifest == b.manifest

    def test_overwrite_different_content_refused(self, store_root):
        f1 = _mkfile(store_root.parent / "w", "snap.parquet", b"PAR1a")
        write_artifact("traces-ingest", "canonical-snapshot", "snap-002", "v0", [f1], good_inputs(), store_root)
        f2 = _mkfile(store_root.parent / "w", "snap.parquet", b"PAR1-DIFFERENT")
        with pytest.raises(StoreWriteError):
            write_artifact("traces-ingest", "canonical-snapshot", "snap-002", "v0", [f2], good_inputs(), store_root)

    def test_duplicate_basenames_rejected(self, store_root):
        d1 = store_root.parent / "a"; d1.mkdir()
        d2 = store_root.parent / "b"; d2.mkdir()
        f1 = _mkfile(d1, "part.parquet", b"one")
        f2 = _mkfile(d2, "part.parquet", b"two")
        with pytest.raises(StoreWriteError):
            write_artifact("traces-ingest", "canonical-snapshot", "snap-003", "v0", [f1, f2], good_inputs(), store_root)

    def test_traversal_id_rejected(self, store_root):
        f = _mkfile(store_root.parent / "w", "snap.parquet", b"PAR1a")
        with pytest.raises(StoreWriteError):
            write_artifact("traces-ingest", "canonical-snapshot", "../escaped", "v0", [f], good_inputs(), store_root)

    def test_wrong_stage_refused(self, store_root):
        f = _mkfile(store_root.parent / "w", "fig.json", b"{}")
        with pytest.raises(StoreWriteError):
            write_artifact(
                "labeling", "figure", "fig-1", "v0",  # figures belong to harness
                [f], good_inputs(), store_root,
            )

    def test_created_at_on_reproducible_fails(self, store_root):
        f = _mkfile(store_root.parent / "w", "snap.parquet", b"PAR1a")
        with pytest.raises(StoreWriteError):
            write_artifact(
                "traces-ingest", "canonical-snapshot", "s2", "v0",
                [f], good_inputs(), store_root, created_at="2026-08-05T10:00:00Z",
            )

    def test_missing_inputs_block_on_reproducible_fails(self, store_root):
        f = _mkfile(store_root.parent / "w", "snap.parquet", b"PAR1a")
        with pytest.raises(StoreWriteError):
            write_artifact(
                "traces-ingest", "canonical-snapshot", "s3", "v0",
                [f], None, store_root,
            )


class TestValidate:
    def _valid_store(self, tmp_path: Path) -> Path:
        root = tmp_path / "store"
        f = _mkfile(tmp_path / "w", "snap.parquet", b"PAR1content")
        write_artifact(
            "traces-ingest", "canonical-snapshot", "snap-001", "v0",
            [f], good_inputs(), root,
        )
        return root

    def test_valid_store_passes(self, tmp_path):
        root = self._valid_store(tmp_path)
        report = validate_store(root)
        assert report.ok, report.errors

    def test_tampered_parquet_detected(self, tmp_path):
        root = self._valid_store(tmp_path)
        target = next((root / "canonical").rglob("*.parquet"))
        data = bytearray(target.read_bytes())
        data[-1] ^= 0xFF
        target.write_bytes(bytes(data))
        report = validate_store(root)
        assert not report.ok
        assert any("sha256" in e for e in report.errors)

    def test_missing_producer_detected(self, tmp_path):
        root = self._valid_store(tmp_path)
        man_path = next((root / "canonical" / "manifests").glob("*.json"))
        man = json.loads(man_path.read_text())
        del man["producer"]
        man_path.write_text(json.dumps(man))
        report = validate_store(root)
        assert not report.ok
        assert any("producer" in e for e in report.errors)

    def test_empty_store_has_stable_documented_version(self, tmp_path):
        root = tmp_path / "store"
        root.mkdir()
        assert compute_store_version(root) == EMPTY_STORE_VERSION


class TestWritersTable:
    def test_ownership_matches_spine(self):
        assert set(WRITERS["labeling"]) == {"labels", "quarantine"}
        assert set(WRITERS["harness"]) == {"figure", "bundle"}
        assert "quarantine" not in WRITERS.get("traces-ingest", ())
