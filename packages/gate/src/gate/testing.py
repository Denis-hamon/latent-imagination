"""Shared test fixtures: pinned snapshot (probe-predictor-v0) + threshold
certificates (story 7.1/7.2).

Tests across gate/ranking/e2e build from HERE — one place to evolve the
artifact schema (the 3-copy drift the 8.2 CR caught)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path

from prereg.certificate import BAR_FORMULA, Certificate, assemble_certificate

FIXTURE_BAR = {"formula": BAR_FORMULA, "cost_exec_usd": 0.0025,
               "cost_regen_usd": 0.0200, "registered_bar": 0.8889}
FIXTURE_SIGNER = {"identity": "fixture-builder", "key_fingerprint": "cd" * 32}


def _fixture_citation(tag: str) -> dict:
    return {"artifact": f"fixture://{tag}", "sha256": sha256(tag.encode()).hexdigest()}


def make_fixture_certificate(
    precision: float = 0.93,
    *,
    generations: tuple[str, ...] = ("probe-gen-a", "probe-gen-b"),
    direction: str = "issued",
    supersedes: str | None = None,
    reason: str | None = None,
) -> Certificate:
    """A structurally valid fixture certificate (content-hash identity)."""
    return assemble_certificate(
        direction=direction,
        verdict_citation=_fixture_citation("verdict"),
        package_citation=_fixture_citation("package"),
        decision_citation=_fixture_citation("decision"),
        generations=generations,
        certified_precision=precision,
        precision_wilson95=(round(max(precision - 0.05, 0.0), 4),
                            round(min(precision + 0.03, 1.0), 4)),
        bar=dict(FIXTURE_BAR),
        signer=dict(FIXTURE_SIGNER),
        supersedes=supersedes,
        supersession_reason=reason,
    )


def certificate_body(cert: Certificate) -> dict:
    return cert.to_dict() | {"certificate_hash": cert.certificate_hash}


def write_certificate_snapshot(root: Path, certs: Sequence[Certificate],
                               candidate: Certificate) -> str:
    """The 7.1 pinned hand-off: certificate.json + supersession-manifest.json.
    Returns the pin (the candidate's CONTENT hash, AD-12)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "certificate.json").write_text(json.dumps(certificate_body(candidate),
                                                      sort_keys=True))
    manifest = {"certificates": {c.certificate_hash: certificate_body(c) for c in certs}}
    (root / "supersession-manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    return candidate.certificate_hash


def make_pinned_snapshot(root: Path, *, corpus_version: str = "corpus-v0"):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    art = {
        "predictor_version": "probe-predictor-v0",
        "corpus_version": corpus_version,
        "measured": {"precision": 0.6271, "note": "Epic-3 matched-control; sub-bar by design (branch iii)"},
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "n_features": 2**12,
                       "alternate_sign": False, "norm": "l2", "lowercase": True,
                       "token_pattern": r"\b\w\w+\b"},
        "model": {"kind": "logreg-sigmoid", "intercept": 0.5, "coefficients": [0.0] * 2**12},
    }
    (root / "META.json").write_text(json.dumps(
        {"layout_version": "store-layout-v1", "store_version": "a" * 64}))
    blob = json.dumps(art, allow_nan=False)
    (root / "predictor.json").write_text(blob)
    return root, sha256(blob.encode()).hexdigest()
