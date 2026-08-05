"""Publication: AD-13 inputs-gate + AD-5 chain assembly."""

from __future__ import annotations

import pytest
from publication.release import ArtifactRef, ReleaseError, assemble_release

CITED = {"store_snapshot": "s" * 64, "ruleset_version": "rules-v1", "code_commit": "c" * 40}


def _ref(i: str, key: str = "ruleset_version", val: str = "rules-v1") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=i,
        artifact_type="figure",
        hash="h" * 64,
        inputs={**CITED, key: val},
    )


def test_release_assembles_when_inputs_match():
    m = assemble_release("r" * 64, "b" * 64, "s" * 64, "e" * 64, "c" * 40, [_ref("fig-1")], CITED)
    assert len(m.chain_hash) == 64


def test_release_refuses_superseded_ruleset_reference():
    with pytest.raises(ReleaseError, match="AD-13"):
        assemble_release(
            "r" * 64, "b" * 64, "s" * 64, "e" * 64, "c" * 40,
            [_ref("fig-old", val="rules-v0")],  # cited rules-v1, artifact says v0
            CITED,
        )
