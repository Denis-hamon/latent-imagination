"""Corpus release assembly (story 4.4): content-cited manifest, drift check,
corpus_version enforcement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from corpus.clean import CleanItem, clean_table
from corpus.publish import assemble_corpus_release, validate_manifest_citations
from store.emit import write_artifact

D = Path(__file__).resolve().parents[3]
GOV = D / "governance"


def _tier(store: Path):
    import tempfile

    import pyarrow.parquet as pq

    item = CleanItem(instance_id="a__a-1", repo="swesmith/x__y.12345678", upstream_repo="x/y",
                     license="MIT", source="swe-smith", f2p_tests=["t"], image_name=None,
                     patch_sha256="a" * 64)
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "items.parquet"
        pq.write_table(clean_table([item]), f)
        write_artifact("corpus", "corpus-item-set", "clean-tier", "v0", [f],
                       {"store_snapshot": "0" * 64, "ruleset_version": "1" * 64,
                        "code_commit": "c" * 40, "seeds": {},
                        "license_inventory_hash": "2" * 64, "corpus_version": "corpus-v0"},
                       store)


class TestCitationEnforcement:
    def test_missing_corpus_version_fails(self):
        with pytest.raises(SchemaError) as ei:
            validate_manifest_citations({"artifact_type": "corpus-release", "inputs": {}})
        assert ei.value.code == "LI-CORPUS-012"

    def test_unrelated_manifest_passes(self):
        validate_manifest_citations({"artifact_type": "figure", "inputs": {"store_snapshot": "x"}})

    def test_wellformed_passes(self):
        validate_manifest_citations({"artifact_type": "corpus-release",
                                     "inputs": {"corpus_version": "corpus-v0"}})


def test_release_assembly_cites_everything_and_verifies_tier_bytes(tmp_path):
    store = tmp_path / "store"
    _tier(store)
    manifest = assemble_corpus_release(store, GOV, major=0, code_commit="c" * 40)
    payload = json.loads(manifest["files"] and (store / "canonical" / "corpus-release-v0" / "v0" / "corpus-release.json").read_text())
    assert payload["corpus_version"] == "corpus-v0"
    assert payload["license_inventory_hash"] and payload["exclusion_rule_hash"]
    assert payload["hardening_policy_hash"] and payload["policy_hash"]
    assert payload["tiers"][0]["artifact_id"] == "clean-tier"
    assert "ADAPTER PENDING" in payload["distribution"]["zenodo"]  # honest, no theater
    assert manifest["inputs"]["corpus_version"] == "corpus-v0"


def test_release_refuses_drifted_tier(tmp_path):
    store = tmp_path / "store"
    _tier(store)
    f = store / "canonical" / "clean-tier" / "v0" / "items.parquet"
    f.write_bytes(f.read_bytes() + b"tamper")
    with pytest.raises(SchemaError) as ei:
        assemble_corpus_release(store, GOV, major=0, code_commit="c" * 40)
    assert ei.value.code == "LI-CORPUS-012"


def test_release_refuses_empty_store(tmp_path):
    with pytest.raises(SchemaError):
        assemble_corpus_release(tmp_path / "empty", GOV, major=0, code_commit="c" * 40)
