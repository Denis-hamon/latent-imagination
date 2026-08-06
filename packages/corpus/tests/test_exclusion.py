"""Exclusion rule + leakage audit + build-check fixture (story 4.2).

AC2: an injected colliding pair FAILS the build — this file proves the check,
not the intention."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from core_schema.errors import SchemaError
from corpus.constituents import build_constituents, instance_repo
from corpus.emit import emit_noisy_item_set
from corpus.exclusion import apply_exclusion, load_rule
from corpus.noisy import build_items

ALLOWLIST = ["MIT"]

D = Path(__file__).resolve().parents[3]
CONSTITUENTS = D / "governance" / "corpus" / "eval-constituents-v1.json"
RULE = D / "governance" / "corpus" / "exclusion-rule-v1.toml"


def _deposit(root: Path, run_id: int, repo: str, sha: str, created: str = "2026-08-01T00:00:00Z"):
    d = root / "ci-logs" / repo.replace("_", "__").replace("/", "-") / str(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "patch.diff").write_bytes(b"diff --git a/x.py b/x.py\n+fix\n")
    (d / "provenance.json").write_text(json.dumps({
        "source": "github-actions", "repo": repo, "head_sha": sha,
        "workflow_run_id": run_id, "run_conclusion": "failure", "license": "MIT",
        "run_created_at": created,
    }))


def _policy(tmp_path):
    import shutil

    dest = tmp_path / "policy.toml"
    shutil.copy(D / "governance" / "corpus" / "harvest-policy-v1.toml", dest)
    return dest


class TestInstanceRepo:
    def test_swe_bench_shape(self):
        assert instance_repo("django__django-16379") == "django/django"
        assert instance_repo("scikit-learn__scikit-learn-25931") == "scikit-learn/scikit-learn"

    def test_swe_smith_shapes(self):
        assert instance_repo("mahmoud__boltons.3bfcfdd0.lm_rewrite__or6ab7bk") == "mahmoud/boltons"
        assert instance_repo(
            "smith::PyCQA__flake8.cf1542ce.combine_file__4w2x9qv4::claude-3-7-sonnet-20250219::0"
        ) == "PyCQA/flake8"

    def test_malformed_is_coded(self):
        with pytest.raises(SchemaError) as ei:
            instance_repo("nodash")
        assert ei.value.code == "LI-CORPUS-007"


def test_committed_constituents_are_sane_and_rule_cites_them():
    payload = json.loads(CONSTITUENTS.read_text())
    assert len(payload["instance_ids"]) > 500  # rebuilt from the sealed probe surfaces
    assert "astropy/astropy" in payload["repos"]
    _rule, constituents, _cpath = load_rule(RULE)
    assert _rule.version == 1 and len(constituents["instance_ids"]) > 500


def test_filter_excludes_collisions_with_audit(tmp_path):
    _deposit(tmp_path, 1, "astropy/astropy", "aaa")   # collides (eval repo)
    _deposit(tmp_path, 2, "clean/lib", "bbb")          # clean
    items = build_items(tmp_path, ALLOWLIST).items
    kept, excluded, audit = apply_exclusion(items, json.loads(CONSTITUENTS.read_text()))
    assert [i.repo for i in kept] == ["clean/lib"]
    assert excluded[0]["reason"] == "repo"
    assert audit["by_reason"] == {"repo": 1, "pr": 0}
    assert audit["examples"][0]["reason"] == "repo"  # examples carry their reason


def test_injected_colliding_pair_is_excluded_with_audit(tmp_path):
    """AC2 build-level: a colliding pair never reaches the artifact; the audit
    inside the artifact documents the exclusion."""
    _deposit(tmp_path, 1, "astropy/astropy", "aaa")  # collides (eval repo)
    _deposit(tmp_path, 2, "clean/lib", "bbb")
    items = build_items(tmp_path, ALLOWLIST).items
    store = tmp_path / "store"
    manifest = emit_noisy_item_set(
        store, items, artifact_id="noisy-tier", artifact_version="v0",
        policy_path=_policy(tmp_path), landing_root=tmp_path,
        exclusion_rule_path=RULE, code_commit="c" * 40,
    )
    assert manifest["inputs"]["leakage_audit"] == {"kept": 1, "excluded": 1, "zero_overlap": True}
    table = pq.read_table(store / "canonical" / "noisy-tier" / "v0" / "items.parquet")
    assert table.num_rows == 1
    assert table.column("repo")[0].as_py() == "clean/lib"


def test_tripwire_raises_on_a_kept_collision(tmp_path):
    """AC2 check-level: the emit tripwire (fresh read of the cited file) does
    raise LI-CORPUS-006 when handed a kept set that collides — the raise the
    build would hit if apply_exclusion were ever broken by a future edit."""
    from corpus.exclusion import assert_no_overlap_cited

    items = build_items(_landing := tmp_path / "l", ALLOWLIST).items
    _deposit(_landing, 1, "astropy/astropy", "aaa")
    items = build_items(_landing, ALLOWLIST).items
    assert items  # one colliding item, unfiltered
    with pytest.raises(SchemaError) as ei:
        assert_no_overlap_cited(items, CONSTITUENTS)
    assert ei.value.code == "LI-CORPUS-006"


def test_exclusion_consuming_entire_set_is_008(tmp_path):
    """Distinct semantics, distinct code: everything filtered out ≠ leakage."""
    _deposit(tmp_path, 1, "astropy/astropy", "aaa")
    items = build_items(tmp_path, ALLOWLIST).items
    with pytest.raises(SchemaError) as ei:
        emit_noisy_item_set(
            tmp_path / "store", items, artifact_id="noisy-tier", artifact_version="v0",
            policy_path=_policy(tmp_path), landing_root=tmp_path,
            exclusion_rule_path=RULE, code_commit="c" * 40,
        )
    assert ei.value.code == "LI-CORPUS-008"


def test_clean_emit_ships_audit_inside_artifact(tmp_path):
    _deposit(tmp_path, 1, "clean/lib", "bbb")
    items = build_items(tmp_path, ALLOWLIST).items
    store = tmp_path / "store"
    manifest = emit_noisy_item_set(
        store, items, artifact_id="noisy-tier", artifact_version="v0",
        policy_path=_policy(tmp_path), landing_root=tmp_path,
        exclusion_rule_path=RULE, code_commit="c" * 40,
    )
    assert "exclusion_rule_hash" in manifest["inputs"]
    assert manifest["inputs"]["leakage_audit"]["zero_overlap"] is True
    audit = json.loads((store / "canonical" / "noisy-tier" / "v0" / "leakage-audit.json").read_text())
    assert audit["kept"] == 1 and audit["excluded"] == 0


def test_constituents_rebuild_from_sealed_surfaces(tmp_path):
    payload = build_constituents(D / "governance" / "probe-design", tmp_path / "c.json")
    assert payload["instance_ids"] == json.loads(CONSTITUENTS.read_text())["instance_ids"]


def test_rule_rejects_stale_constituents_hash(tmp_path):
    import shutil

    gov = tmp_path / "governance" / "corpus"
    gov.mkdir(parents=True)
    stale = gov / "rule.toml"
    shutil.copy(RULE, stale)
    (gov / "c.json").write_text(json.dumps({"instance_ids": [], "repos": ["x/y"], "prs": []}))
    stale.write_text(stale.read_text().replace(
        "governance/corpus/eval-constituents-v1.json", "governance/corpus/c.json"
    ))
    with pytest.raises(SchemaError) as ei:
        load_rule(stale)
    assert ei.value.code == "LI-CORPUS-007"


def test_dotted_repo_names_survive_parsing():
    """CR 4.2 HIGH regression: task-hash split never truncates dotted repos."""
    from corpus.constituents import instance_repo

    assert instance_repo("mrdoob__three.js.8f4a2c1d.func__salt") == "mrdoob/three.js"
    assert instance_repo("a.b__c.d-e") == "a.b/c.d-e"  # dots + dash, no task hash


def test_repo_matching_is_casefolded(tmp_path):
    """CR 4.2 med regression: GitHub names are case-insensitive — 'Django/Django'
    must collide with constituent 'django/django'."""
    _deposit(tmp_path, 1, "Django/Django", "aaa")
    items = build_items(tmp_path, ALLOWLIST).items
    kept, excluded, _audit = apply_exclusion(items, json.loads(CONSTITUENTS.read_text()))
    assert kept == [] and len(excluded) == 1
