"""Release assembly — chain manifest + inputs gate (AD-13) + anchor wiring.

The AD-5 topology lives in prereg.assemble_chain (never reimplemented here).
This module: (1) verifies every artifact's inputs against what the release
CITES (2) assembles the chain (3) hands the chain hash to the anchor adapter.
Pushers (S3/Zenodo/HF) are adapter calls made BY the ceremony, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prereg.chain import ChainManifest, assemble_chain


class ReleaseError(Exception):
    code = "LI-PUB-001"


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    artifact_type: str
    hash: str
    inputs: dict[str, Any]


def verify_inputs(artifacts: list[ArtifactRef], cited_versions: dict[str, str]) -> None:
    """Every artifact's inputs must match the versions the release cites."""
    for art in artifacts:
        for key in ("store_snapshot", "ruleset_version", "code_commit"):
            cited = cited_versions.get(key)
            carried = art.inputs.get(key)
            if cited is not None and carried != cited:
                raise ReleaseError(
                    f"{art.artifact_id}: inputs.{key}={carried!r} != cited {cited!r} (AD-13)"
                )


def assemble_release(
    release_hash: str,
    bundle_hash: str,
    snapshot_hash: str,
    ruleset_hash: str,
    code_commit: str,
    artifacts: list[ArtifactRef],
    cited_versions: dict[str, str],
) -> ChainManifest:
    verify_inputs(artifacts, cited_versions)
    return assemble_chain(release_hash, bundle_hash, snapshot_hash, ruleset_hash, code_commit)
