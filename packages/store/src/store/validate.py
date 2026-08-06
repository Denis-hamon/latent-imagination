"""store-validate — the public verifier any reproducer can run (AD-8).

Hardened (review 2026-08-05): META recomputed, ownership re-checked, AD-7
hygiene, hash + append-only + non-crashing on corruption (errors, not
exceptions), fail-closed precedence when a ledger exists.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from store.emit import WRITERS, compute_store_version
from store.layout import LAYOUT_VERSION, REPRODUCIBLE_CLASSES


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _sha256_file(p: Path) -> str:
    h = sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_manifest(root: Path, mpath: Path, man: dict, report: ValidationReport, seen: dict) -> None:
    producer = man.get("producer")
    atype = man.get("artifact_type")
    if not producer:
        report.errors.append(f"{mpath.name}: missing producer field")
    elif atype in WRITERS.get(producer, ()):
        pass  # ownership holds
    elif producer in WRITERS:
        report.errors.append(
            f"{mpath.name}: producer '{producer}' does not own artifact_type '{atype}'"
        )
    else:
        report.errors.append(f"{mpath.name}: unknown producer '{producer}'")

    if atype in REPRODUCIBLE_CLASSES and "created_at" in man:
        report.errors.append(f"{mpath.name}: reproducible manifest carries created_at (AD-7)")

    for fe in man.get("files", []):
        fpath = (root / fe.get("path", "")).resolve()
        try:
            fpath.relative_to(root.resolve())
        except ValueError:
            report.errors.append(f"{mpath.name}: file path escapes store root: {fe.get('path')}")
            continue
        if not fpath.exists():
            report.errors.append(f"{mpath.name}: missing file {fe.get('path')}")
            continue
        if _sha256_file(fpath) != fe.get("sha256"):
            report.errors.append(f"{mpath.name}: sha256 mismatch on {fe.get('path')}")

    # AD-13 teeth (story 4.4): corpus-touching manifests must cite corpus_version.
    _inputs = man.get("inputs") or {}
    _corpusish = (
        str(man.get("artifact_type", "")).startswith("corpus")
        or {"corpus_version", "corpus_tier", "tiers_cited"} & set(_inputs)
    )
    if _corpusish:
        import re as _re

        v = _inputs.get("corpus_version")
        ok = isinstance(v, str) and _re.fullmatch(r"corpus-v(0|[1-9][0-9]*)", v) is not None
        if not ok:
            report.errors.append(
                f"{mpath.name}: corpus-touching manifest without a parseable corpus_version "
                f"(LI-CORPUS contract) — got {v!r}"
            )

    key = (man.get("artifact_id", "?"), man.get("artifact_version", "?"))
    blob = "|".join(sorted(fe.get("sha256", "") for fe in man.get("files", [])))
    if key in seen and seen[key] != blob:
        report.errors.append(
            f"{mpath.name}: append-only violation — {key} re-published with different content"
        )
    seen[key] = blob


def validate_store(root: Path) -> ValidationReport:
    root = Path(root)
    report = ValidationReport()

    meta_path = root / "META.json"
    if not meta_path.exists():
        report.errors.append("META.json missing at store root")
        report.checks["meta"] = "failed"
        return report
    try:
        meta = json.loads(meta_path.read_text())
    except json.JSONDecodeError as e:
        report.errors.append(f"META.json invalid: {e}")
        report.checks["meta"] = "failed"
        return report
    if meta.get("layout_version") != LAYOUT_VERSION:
        report.errors.append(
            f"layout_version mismatch: {meta.get('layout_version')} != {LAYOUT_VERSION}"
        )
    recomputed = compute_store_version(root)
    if meta.get("store_version") != recomputed:
        report.errors.append("META.store_version does not recompute from canonical content")
    report.checks["meta"] = "failed" if report.errors else "ok"

    seen: dict = {}
    parsed: list[dict] = []
    manifests = sorted(root.glob("**/manifests/*.artifact.json"))
    if not manifests:
        report.warnings.append("no artifact manifests found (empty store?)")
    report.checks["manifest-presence"] = "ok" if manifests else "skipped"
    for mpath in manifests:
        try:
            man = json.loads(mpath.read_text())
        except (json.JSONDecodeError, OSError) as e:
            report.errors.append(f"{mpath.name}: unreadable manifest: {e}")
            continue
        parsed.append(man)
        _check_manifest(root, mpath, man, report, seen)

    report.checks["hashes"] = "ok" if not any("sha256" in e for e in report.errors) else "failed"
    report.checks["append-only"] = "ok" if not any("append-only" in e for e in report.errors) else "failed"
    report.checks["ownership"] = "ok" if not any("own" in e or "producer" in e for e in report.errors) else "failed"
    report.checks["ad7-hygiene"] = "ok" if not any("AD-7" in e for e in report.errors) else "failed"

    ledger = root / "prereg-ledger.jsonl"
    if ledger.exists():
        try:
            from prereg.chain import verify_chain_precedence  # type: ignore
        except ImportError:
            report.errors.append(
                "prereg package not importable but ledger present (fail-closed)"
            )
            report.checks["prereg-precedence"] = "failed"
        else:
            verdict = verify_chain_precedence(ledger, parsed)
            report.checks["prereg-precedence"] = verdict.status
            if verdict.status != "ok":
                report.errors.append(f"prereg precedence: {verdict.detail}")
    else:
        report.checks["prereg-precedence"] = "skipped"
    return report


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: store-validate <store_root>", file=sys.stderr)
        return 2
    report = validate_store(Path(argv[1]))
    for k, v in report.checks.items():
        print(f"{k}: {v}")
    for w in report.warnings:
        print(f"WARN: {w}", file=sys.stderr)
    for e in report.errors:
        print(f"FAIL: {e}", file=sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
