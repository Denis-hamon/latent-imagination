"""Exclusion rule + leakage audit + build-check fixture (story 4.2).

AC2: an injected colliding pair FAILS the build — this file proves the check,
not the intention."""

from __future__ import annotations

import json
from pathlib import Path

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
    rule = load_rule(RULE)
    assert rule.version == 1  # load_rule already verified the cited hash


def test_filter_excludes_collisions_with_audit(tmp_path):
    _deposit(tmp_path, 1, "astropy/astropy", "aaa")   # collides (eval repo)
    _deposit(tmp_path, 2, "clean/lib", "bbb")          # clean
    items = build_items(tmp_path, ALLOWLIST).items
    kept, excluded, audit = apply_exclusion(items, json.loads(CONSTITUENTS.read_text()))
    assert [i.repo for i in kept] == ["clean/lib"]
    assert excluded[0]["reason"] == "repo"
    assert audit["zero_overlap"] is True
    assert audit["by_reason"] == {"repo": 1}
    assert audit["examples"]


def test_injected_colliding_pair_fails_the_build(tmp_path):
    """AC2 — the emit path itself refuses when a collision survives."""
    _deposit(tmp_path, 1, "astropy/astropy", "aaa")
    items = build_items(tmp_path, ALLOWLIST).items
    with pytest.raises(SchemaError) as ei:
        emit_noisy_item_set(
            tmp_path / "store", items, artifact_id="noisy-tier", artifact_version="v0",
            policy_path=_policy(tmp_path), landing_root=tmp_path,
            exclusion_rule_path=RULE, constituents_path=CONSTITUENTS,
            code_commit="c" * 40,
        )
    assert ei.value.code == "LI-CORPUS-006"


def test_clean_emit_ships_audit_inside_artifact(tmp_path):
    _deposit(tmp_path, 1, "clean/lib", "bbb")
    items = build_items(tmp_path, ALLOWLIST).items
    store = tmp_path / "store"
    manifest = emit_noisy_item_set(
        store, items, artifact_id="noisy-tier", artifact_version="v0",
        policy_path=_policy(tmp_path), landing_root=tmp_path,
        exclusion_rule_path=RULE, constituents_path=CONSTITUENTS, code_commit="c" * 40,
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

    stale = tmp_path / "rule.toml"
    shutil.copy(RULE, stale)
    (tmp_path / "c.json").write_text(json.dumps({"instance_ids": [], "repos": ["x/y"], "prs": []}))
    stale.write_text(stale.read_text().replace(
        "governance/corpus/eval-constituents-v1.json", str(tmp_path / "c.json")
    ))
    with pytest.raises(SchemaError) as ei:
        load_rule(stale)
    assert ei.value.code == "LI-CORPUS-007"
