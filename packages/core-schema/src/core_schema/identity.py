"""Canonical identity derivation (AD-12).

The ONLY place attempt/task identity is computed. Rules:

- Canonical JSON: sort_keys + tight separators; hashing is sha256 hex.
- Diff text is normalized (CRLF→LF, trailing whitespace stripped) before hashing,
  so byte-formatting variance never re-mints an id.
- Timezone: naive → LI-SCHEMA-002; aware non-UTC → normalized to UTC.
- Fingerprint hashing is dict-order-invariant by construction.
- The attempt window start IS part of identity (two materially identical attempts
  are different attempts; flakiness analysis depends on that distinction, FR-4).
"""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Any

from core_schema.domain import EnvironmentFingerprint
from core_schema.errors import ensure_aware_utc


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(s: str) -> str:
    return sha256(s.encode("utf-8")).hexdigest()


def normalize_diff(diff_text: str) -> str:
    """CRLF→LF, then strip trailing whitespace per the identity rule."""
    return diff_text.replace("\r\n", "\n").rstrip() + "\n"


def fingerprint_hash(fp: EnvironmentFingerprint) -> str:
    """Dict-order invariant: canonical JSON sorts keys before hashing."""
    return _sha(_canon(fp.model_dump(mode="json")))


def task_fingerprint(
    repo_full_name: str, commit_sha: str, f2p_tests: tuple[str, ...] | list[str]
) -> str:
    tests = sorted(set(f2p_tests))
    return _sha(
        _canon(
            {
                "repo_full_name": repo_full_name,
                "commit_sha": commit_sha,
                "f2p_tests": tests,
            }
        )
    )


def attempt_id(
    task_id: str,
    patch_diff: str,
    env_fingerprint: EnvironmentFingerprint,
    attempt_start: datetime,
) -> str:
    """Canonical attempt identity (FR-2). Same logical attempt from two sources
    must land on the same id — that is what enables cross-source dedup."""
    start = ensure_aware_utc(attempt_start, "attempt_start")
    return _sha(
        _canon(
            {
                "task_id": task_id,
                "patch_sha256": _sha(normalize_diff(patch_diff)),
                "env_fingerprint_sha256": fingerprint_hash(env_fingerprint),
                "attempt_start_utc": start.isoformat().replace("+00:00", "Z"),
            }
        )
    )
