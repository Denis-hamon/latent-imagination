"""Design package content hash — what gets anchored at the freeze ceremony.

Deterministic: canonical JSON over each file's sha256, sorted by relative path.
Cache/OS litter excluded; the manifest (package-manifest.json) is written next
to the hashed set — printed AND recorded.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path


def design_package_hash(directory: Path) -> tuple[str, dict[str, str]]:
    """Deterministic: canonical JSON over relative-path-keyed file sha256s.
    Returns (hash, per-file map) so the manifest can be written AND verified.
    Excludes byte-compiled caches and OS/editor litter from the anchored set."""
    directory = Path(directory)
    skip_names = {".DS_Store", "package-manifest.json"}
    entries: dict[str, str] = {}
    for f in sorted(directory.rglob("*")):
        if not f.is_file():
            continue
        rel = str(f.relative_to(directory))
        if "__pycache__" in f.parts or f.name in skip_names:
            continue
        entries[rel] = sha256(f.read_bytes()).hexdigest()
    canon = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return sha256(canon.encode()).hexdigest(), entries


def write_manifest(directory: Path) -> Path:
    h, entries = design_package_hash(directory)
    out = Path(directory) / "package-manifest.json"
    out.write_text(
        json.dumps(
            {"package": Path(directory).name, "package_hash": h, "files": entries},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return out


if __name__ == "__main__":
    import sys

    h, entries = design_package_hash(Path(sys.argv[1]))
    print(json.dumps({"package_hash": h, "files": entries}, indent=2, sort_keys=True))
