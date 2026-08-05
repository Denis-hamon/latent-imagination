#!/usr/bin/env bash
# Pre-registration ceremony: anchor a chain_hash via OTS calendars.
set -euo pipefail
: "${1:?usage: ceremony.sh <chain_hash>}"
: "${STORE_ROOT:?set STORE_ROOT}"
uv run --package li-ots-anchor python - "$1" "$STORE_ROOT" << 'PY'
import sys
from ots_anchor.anchor import anchor, AnchorUnavailableError
try:
    rec = anchor(sys.argv[1], f"{sys.argv[2]}/proofs/{sys.argv[1][:16]}.ots")
except AnchorUnavailableError as e:
    print(f"ANCHOR UNAVAILABLE: {e}", file=sys.stderr)
    sys.exit(42)
print(rec.anchored_at)
PY
PY
