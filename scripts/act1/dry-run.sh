#!/usr/bin/env bash
# Act I dry-run: a "stranger" pass from a FRESH container/env following only the
# public docs. No project venv assumed; only what STRANGER.md names.
set -euo pipefail

BUNDLE="${1:?usage: dry-run.sh <bundle_dir>}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> fresh venv, install only the bundle's declared needs (python stdlib + duckdb)"
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet duckdb

echo "==> follow STRANGER.md: recompute"
"$WORK/venv/bin/python" "$BUNDLE/pipeline/run.py" \
  --slice "$BUNDLE/slice" --out "$WORK/out"

echo "==> compare against expected.json"
"$WORK/venv/bin/python" - "$WORK/out" "$BUNDLE/expected.json" << 'PY'
import json, sys
from hashlib import sha256
from pathlib import Path

out = Path(sys.argv[1])
expected = json.loads(Path(sys.argv[2]).read_text())
produced = {
    str(f.relative_to(out)): sha256(f.read_bytes()).hexdigest()
    for f in sorted(out.rglob("*")) if f.is_file()
}
missing = {k for k, v in expected.items() if produced.get(k) != v}
extras = set(produced) - set(expected)
if missing or extras:
    print("DIVERGENCE:", sorted(missing | extras))
    sys.exit(1)
print("PASS — figures recomputed identically")
PY
