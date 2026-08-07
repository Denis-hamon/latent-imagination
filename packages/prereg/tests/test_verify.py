"""verify_proof_bytes (deferred-work Epic-1 M-1, closed 2026-08-06): the REAL
committed .ots proof byte-parses and binds to its chain."""

from __future__ import annotations

from pathlib import Path

from prereg.chain import ChainManifest
from prereg.verify import verify_proof_bytes

REPO_ROOT = Path(__file__).resolve().parents[3]
PROOF = REPO_ROOT / "data" / "release-store" / "proofs" / "3ff03b8a7f393c57.ots"
CHAIN = "3ff03b8a7f393c57c23e6ed553d6db0b684cecb8f41b512877d27acd1276f6b7"


def _man(chain: str) -> ChainManifest:
    return ChainManifest(release="r", bundle="b", snapshot="s", ruleset="rs",
                         code_commit="c", chain_hash=chain)


def test_real_live_anchor_proof_parses_and_binds():
    assert PROOF.is_file(), "the live OTS proof should be committed"
    rep = verify_proof_bytes(_man(CHAIN), PROOF)
    assert rep.ok, rep.errors


def test_mismatched_chain_refused():
    rep = verify_proof_bytes(_man("f" * 64), PROOF)
    assert not rep.ok and "digest" in rep.errors[0]


def test_missing_proof_coded(tmp_path):
    rep = verify_proof_bytes(_man("f" * 64), tmp_path / "none.ots")
    assert not rep.ok and "proof missing" in rep.errors[0]
