from ots_anchor.anchor import anchor_offline_simulated


def test_simulated_anchor_shape():
    r = anchor_offline_simulated("ab" * 32, "proofs/x.ots")
    assert r.chain_hash == "ab" * 32
    assert r.anchored_at.endswith("Z")
