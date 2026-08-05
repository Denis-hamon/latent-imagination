"""prereg pure-lib contract: chain assembly, offline verify, precedence hook.

Design note (decided here): label manifests stay reproducible-class (no
timestamps). Precedence is judged from the store's `prereg-ledger.jsonl`, which
contains BOTH anchor records AND run entries {type: run, run_id, started_at};
label manifests reference their run via inputs.run_id.
"""

from __future__ import annotations

import json
from pathlib import Path

from prereg.anchor_format import AnchorRecord
from prereg.chain import assemble_chain, verify_chain_precedence
from prereg.verify import verify_offline


class TestChainAssembly:
    def test_shape_fixed_and_content_only(self):
        m = assemble_chain(
            release_hash="r" * 64,
            bundle_hash="b" * 64,
            snapshot_hash="s" * 64,
            ruleset_hash="e" * 64,
            code_commit="c" * 40,
        )
        man = m.to_dict()
        assert set(man) == {"release", "bundle", "snapshot", "ruleset", "code_commit", "chain_hash"}
        assert "created_at" not in man
        assert m.chain_hash == assemble_chain("r" * 64, "b" * 64, "s" * 64, "e" * 64, "c" * 40).chain_hash

    def test_order_matters(self):
        a = assemble_chain("a" * 64, "b" * 64, "s" * 64, "e" * 64, "c" * 40)
        b = assemble_chain("b" * 64, "a" * 64, "s" * 64, "e" * 64, "c" * 40)
        assert a.chain_hash != b.chain_hash


class TestAnchorRecord:
    def test_occurrence_class_allows_timestamps(self):
        r = AnchorRecord(chain_hash="x" * 64, ots_proof_ref="p.ots", anchored_at="2026-08-05T10:00:00Z")
        assert r.anchored_at


class TestVerifyOffline:
    def test_structure_ok(self):
        m = assemble_chain("r" * 64, "b" * 64, "s" * 64, "e" * 64, "c" * 40)
        rec = AnchorRecord(chain_hash=m.chain_hash, ots_proof_ref="proofs/x.ots", anchored_at="2026-08-05T10:00:00Z")
        assert verify_offline(m, rec).ok

    def test_tamper_detected_offline(self):
        m = assemble_chain("r" * 64, "b" * 64, "s" * 64, "e" * 64, "c" * 40)
        rec = AnchorRecord(chain_hash="9" * 64, ots_proof_ref="proofs/x.ots", anchored_at="2026-08-05T10:00:00Z")
        rep = verify_offline(m, rec)
        assert not rep.ok
        assert "chain_hash" in rep.errors[0]


class TestPrecedence:
    def _run(self, run_id: str, started_at: str, ruleset_hash: str = "e" * 64) -> dict:
        return {"type": "run", "run_id": run_id, "started_at": started_at, "ruleset_hash": ruleset_hash}

    def _anchor(self, anchored_at: str, ruleset_hash: str = "e" * 64) -> dict:
        return {"type": "anchor", "ruleset_hash": ruleset_hash, "anchored_at": anchored_at, "chain_hash": "x" * 64, "ots_proof_ref": "p.ots"}

    def _label_manifest(self, run_id: str) -> dict:
        return {
            "artifact_type": "labels",
            "inputs": {"run_id": run_id, "ruleset_version": "rules-v1"},
            "files": [],
        }

    def _ledger(self, tmp_path: Path, entries: list[dict]) -> Path:
        p = tmp_path / "prereg-ledger.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        return p

    def test_anchor_before_run_ok(self, tmp_path):
        ledger = self._ledger(tmp_path, [
            self._anchor("2026-08-04T10:00:00Z"),
            self._run("run-1", "2026-08-05T10:00:00Z"),
        ])
        v = verify_chain_precedence(ledger, [self._label_manifest("run-1")])
        assert v.status == "ok"

    def test_anchor_after_run_violation(self, tmp_path):
        ledger = self._ledger(tmp_path, [
            self._anchor("2026-08-06T10:00:00Z"),
            self._run("run-1", "2026-08-05T10:00:00Z"),
        ])
        v = verify_chain_precedence(ledger, [self._label_manifest("run-1")])
        assert v.status == "violation"
        assert "anchored after" in v.detail

    def test_missing_anchor_violation(self, tmp_path):
        ledger = self._ledger(tmp_path, [self._run("run-1", "2026-08-05T10:00:00Z")])
        v = verify_chain_precedence(ledger, [self._label_manifest("run-1")])
        assert v.status == "violation"

    def test_ignores_occurrence_artifacts_in_manifests(self, tmp_path):
        ledger = self._ledger(tmp_path, [self._anchor("2026-08-04T10:00:00Z"), self._run("run-1", "2026-08-05T10:00:00Z")])
        man = self._label_manifest("run-1")
        man["artifact_type"] = "canonical-snapshot"  # not a label-set
        v = verify_chain_precedence(ledger, [man])
        assert v.status == "ok"
