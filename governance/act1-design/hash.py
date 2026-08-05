"""Design package content hash — what gets anchored at the freeze ceremony.

Deterministic: canonical JSON over each file's sha256, sorted by filename.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path


def design_package_hash(directory: Path) -> str:
    directory = Path(directory)
    entries = {
        f.name: sha256(f.read_bytes()).hexdigest()
        for f in sorted(directory.rglob("*"))
        if f.is_file() and f.suffix not in {".sha256"}
    }
    canon = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return sha256(canon.encode()).hexdigest()


if __name__ == "__main__":
    import sys

    print(design_package_hash(Path(sys.argv[1])))
