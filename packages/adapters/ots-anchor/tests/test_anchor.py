import os

import pytest
from ots_anchor.anchor import AnchorUnavailableError, anchor, anchor_offline_simulated


def test_simulated_anchor_shape():
    r = anchor_offline_simulated("ab" * 32, "proofs/x.ots")
    assert r.chain_hash == "ab" * 32
    assert r.anchored_at.endswith("Z")


@pytest.mark.skipif(
    not os.environ.get("LI_OTS_LIVE"),
    reason="live OTS calendars — opt-in via LI_OTS_LIVE=1 (deferred-work Epic-1)",
)
def test_live_anchor_stamps(tmp_path):
    try:
        rec = anchor("ab" * 32, str(tmp_path / "p.ots"))
    except AnchorUnavailableError as e:
        pytest.skip(f"calendars unreachable from this host: {e}")
    assert (tmp_path / "p.ots").exists()
    assert rec.chain_hash == "ab" * 32
    assert rec.ots_proof_ref.endswith("p.ots")
