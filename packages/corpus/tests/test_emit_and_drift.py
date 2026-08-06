"""Emit (store contract) + ATIF drift watch (Tasks 2)."""

from __future__ import annotations

import json

import pyarrow.parquet as pq
import pytest
from corpus.atif_drift import watch
from corpus.emit import emit_noisy_item_set
from corpus.noisy import build_items

ALLOWLIST = ["MIT"]
REAL_POLICY = (
    __import__("pathlib").Path(__file__).resolve().parents[3]
    / "governance" / "corpus" / "harvest-policy-v1.toml"
)


def _copy_policy(tmp_path):
    import shutil

    dest = tmp_path / "policy.toml"
    shutil.copy(REAL_POLICY, dest)
    return dest


def _exclusion_fixture(tmp_path):
    """A colliding-free constituents + matching rule, laid out as the binding
    requires: rule under <root>/governance/corpus/, constituents_file relative
    to <root> (hashes computed live)."""
    import json as _json
    from hashlib import sha256

    c = tmp_path / "governance" / "corpus" / "constituents.json"
    c.parent.mkdir(parents=True)
    c.write_text(_json.dumps({"version": 1, "sources": [], "instance_ids": ["z__z-1"], "repos": ["z/z"], "prs": []}))
    r = c.parent / "rule.toml"
    r.write_text(
        f'[rule]\nversion = 1\nconstituents_file = "governance/corpus/constituents.json"\n'
        f'constituents_sha256 = "{sha256(c.read_bytes()).hexdigest()}"\nstrategy = "t"\n'
    )
    return r, c


def _one_item_landing(tmp_path):
    d = tmp_path / "landing" / "ci-logs" / "o_per_r" / "101"
    d.mkdir(parents=True)
    (d / "patch.diff").write_bytes(b"diff --git a/x.py b/x.py\n+a\n")
    (d / "provenance.json").write_text(json.dumps({
        "repo": "o/r", "head_sha": "abc123", "workflow_run_id": 101,
        "run_conclusion": "failure", "license": "MIT", "run_created_at": "2026-08-01T00:00:00Z",
    }))
    (tmp_path / "landing" / "ci-logs" / "o_per_r" / ".harvest-manifest.json").write_text("{}")
    return tmp_path / "landing"


def test_emit_writes_reproducible_canonical_artifact(tmp_path):
    from corpus.policy import load_policy

    landing = _one_item_landing(tmp_path)
    items = build_items(landing, ALLOWLIST).items
    store = tmp_path / "store"
    policy_path = _copy_policy(tmp_path)
    assert load_policy(policy_path).version == 1
    manifest = emit_noisy_item_set(
        store, items, artifact_id="noisy-tier", artifact_version="v0",
        policy_path=policy_path, landing_root=landing, code_commit="c" * 40,
        exclusion_rule_path=_exclusion_fixture(tmp_path)[0],
    )
    assert manifest["artifact_class"] == "reproducible"
    assert manifest["producer"] == "corpus"
    assert manifest["artifact_type"] == "corpus-item-set"
    assert "created_at" not in manifest  # AD-7
    assert manifest["inputs"]["code_commit"] == "c" * 40
    assert len(manifest["inputs"]["ruleset_version"]) == 64
    table = pq.read_table(store / "canonical" / "noisy-tier" / "v0" / "items.parquet")
    assert table.num_rows == 1
    assert json.loads(table.column("sanitize_counts")[0].as_py()) == {}


def test_emit_refuses_empty_and_non_corpus_producer_fails(tmp_path):
    landing = _one_item_landing(tmp_path)
    store = tmp_path / "store"
    policy_path = _copy_policy(tmp_path)
    from core_schema.errors import SchemaError

    with pytest.raises(SchemaError) as ei:
        rule, _const = _exclusion_fixture(tmp_path)
        emit_noisy_item_set(store, [], artifact_id="noisy-tier", artifact_version="v0",
                            policy_path=policy_path, landing_root=landing,
                            exclusion_rule_path=rule)
    assert ei.value.code == "LI-CORPUS-004"
    # AD-4: the emit table itself refuses a foreign stage for this artifact type
    from store.emit import StoreWriteError, write_artifact

    f = tmp_path / "x.parquet"
    f.write_bytes(b"PAR1")
    with pytest.raises(StoreWriteError):
        write_artifact("harness", "corpus-item-set", "noisy-tier", "v0", [f],
                       {"store_snapshot": "0" * 64, "ruleset_version": "1" * 64,
                        "code_commit": "c" * 40, "seeds": {}}, store)


def test_drift_watch_reports_versions_seen(tmp_path):
    traj_dir = tmp_path / "atif-src" / "b1"
    traj_dir.mkdir(parents=True)
    (traj_dir / "ok.json").write_text(json.dumps({"schema_version": "ATIF-v1.7"}))
    (traj_dir / "drifted.json").write_text(json.dumps({"schema_version": "ATIF-v9.9"}))
    (traj_dir / ".landing-manifest.json").write_text("{}")
    (traj_dir / "broken.json").write_text("{ nope")
    rep = watch(tmp_path, "ATIF-v1.7")
    assert rep.scanned == 2 and rep.matched == 1  # unparseable counted apart
    assert rep.observed == {"ATIF-v1.7": 1, "ATIF-v9.9": 1}
    assert rep.unparseable == 1
    assert rep.drift is True


def test_drift_watch_empty_landing_no_drift(tmp_path):
    rep = watch(tmp_path, "ATIF-v1.7")
    assert rep.scanned == 0 and rep.drift is False


def test_emit_git_fallback_fails_loud(tmp_path):
    """P17: no fabricated 40-zero code_commit — LI-CORPUS-005 instead."""
    from core_schema.errors import SchemaError

    landing = _one_item_landing(tmp_path)
    items = build_items(landing, ALLOWLIST).items
    with pytest.raises(SchemaError) as ei:
        rule, _const2 = _exclusion_fixture(tmp_path)
        emit_noisy_item_set(tmp_path / "s", items, artifact_id="noisy-tier", artifact_version="v0",
                            policy_path=_copy_policy(tmp_path), landing_root=landing,
                            exclusion_rule_path=rule,
                            repo_root=tmp_path / "definitely-not-a-repo")
    assert ei.value.code == "LI-CORPUS-005"


def test_write_report_persists_occurrence(tmp_path):
    """P7: the drift watch has a real invocation surface writing an occurrence report."""
    traj = tmp_path / "landing" / "src" / "b1"
    traj.mkdir(parents=True)
    (traj / "ok.json").write_text(json.dumps({"schema_version": "ATIF-v1.7"}))
    from corpus.atif_drift import write_report

    out = write_report(tmp_path / "landing", "ATIF-v1.7")
    assert out.name == "atif-drift-report.json"
    payload = json.loads(out.read_text())
    assert payload["matched"] == 1 and "created_at" in payload
