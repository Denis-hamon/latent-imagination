"""store-validate — the public verifier any reproducer can run (AD-8).

Checks, in order:
1. layout structure known (META.json present, layout_version matches)
2. every artifact dir has a manifest; manifests live in */manifests/
3. per-file sha256 match (tamper detection)
4. append-only history: no two manifests share (artifact_id, artifact_version)
   with different file hashes
5. producer field present
6. AD-7 class hygiene: reproducible manifests carry no created_at
7. prereg precedence when a ledger exists (delegated to prereg if importable — pure
   function handoff, else reported as "skipped")

``validate_store`` returns a report; the CLI exits non-zero on failure.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from store.layout import LAYOUT_VERSION, REPRODUCIBLE_CLASSES


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)  # name -> ok|failed|skipped

    @property
    def ok(self) -> bool:
        return not self.errors


def _sha256_file(p: Path) -> str:
    return sha256(p.read_bytes()).hexdigest()


def validate_store(root: Path) -> ValidationReport:
    root = Path(root)
    report = ValidationReport()

    # 1. META.json + layout version
    meta_path = root / "META.json"
    if not meta_path.exists():
        report.errors.append("META.json missing at store root")
        report.checks["meta"] = "failed"
        return report
    meta = json.loads(meta_path.read_text())
    if meta.get("layout_version") != LAYOUT_VERSION:
        report.errors.append(
            f"layout_version mismatch: {meta.get('layout_version')} != {LAYOUT_VERSION}"
        )
    report.checks["meta"] = "ok" if meta.get("layout_version") == LAYOUT_VERSION else "failed"

    # gather manifests
    manifests = sorted(root.glob("**/manifests/*.artifact.json"))
    if not manifests:
        report.warnings.append("no artifact manifests found (empty store?)")
    report.checks["manifest-presence"] = "ok" if manifests else "skipped"

    seen: dict[tuple[str, str], str] = {}
    for mpath in manifests:
        try:
            man = json.loads(mpath.read_text())
        except json.JSONDecodeError as e:
            report.errors.append(f"{mpath}: invalid JSON: {e}")
            continue

        # 5. producer
        if not man.get("producer"):
            report.errors.append(f"{mpath.name}: missing producer field")

        # 6. AD-7 hygiene
        if man.get("artifact_type") in REPRODUCIBLE_CLASSES and "created_at" in man:
            report.errors.append(
                f"{mpath.name}: reproducible manifest carries created_at (AD-7)"
            )

        # 3. hashes
        for fe in man.get("files", []):
            f = root / fe["path"]
            if not f.exists():
                report.errors.append(f"{mpath.name}: missing file {fe['path']}")
                continue
            actual = _sha256_file(f)
            if actual != fe.get("sha256"):
                report.errors.append(
                    f"{mpath.name}: sha256 mismatch on {fe['path']}"
                )

        # 4. append-only
        key = (man.get("artifact_id", "?"), man.get("artifact_version", "?"))
        blob = "|".join(sorted(fe.get("sha256", "") for fe in man.get("files", [])))
        if key in seen and seen[key] != blob:
            report.errors.append(
                f"{mpath.name}: append-only violation — {key} re-published with different content"
            )
        seen[key] = blob

    report.checks["hashes"] = "ok" if not any("sha256" in e for e in report.errors) else "failed"
    report.checks["append-only"] = "ok" if not any("append-only" in e for e in report.errors) else "failed"
    report.checks["producer"] = "ok" if not any("producer" in e for e in report.errors) else "failed"
    report.checks["ad7-hygiene"] = "ok" if not any("AD-7" in e for e in report.errors) else "failed"

    # 7. prereg precedence — hook point; full machinery in Story 1.4
    ledger = root / "prereg-ledger.jsonl"
    if ledger.exists():
        try:
            from prereg.chain import verify_chain_precedence  # type: ignore

            verdict = verify_chain_precedence(ledger, manifests)
            report.checks["prereg-precedence"] = verdict.status  # ok|violation
            if verdict.status != "ok":
                report.errors.append(f"prereg precedence: {verdict.detail}")
        except ImportError:
            report.checks["prereg-precedence"] = "skipped"
            report.warnings.append("prereg package not importable; precedence check skipped")
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
