"""Sanitizer — secrets/PII redaction with counts, fail-closed (FR-2).

Pattern policy is FROZEN (governance/sanitize-policy.toml): editing it is a
pre-registered change event. Unknown-looking high-entropy strings near
"token"/"key" markers are rejected (fail closed), not silently passed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PATTERNS: dict[str, str] = {
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "github_token": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "openai_key": r"sk-[A-Za-z0-9_-]{20,}",
    "private_key_block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "generic_assignment_token": r"(?i)(token|api[_-]?key|secret)\s*[:=]\s*['\"]?[A-Za-z0-9/_+\-.]{16,}['\"]?",
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
}

REDACTED = "[REDACTED]"


@dataclass
class SanitizeResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def sanitize_text(text: str) -> SanitizeResult:
    counts: dict[str, int] = {}
    out = text
    for name, pattern in PATTERNS.items():
        out, n = re.subn(pattern, REDACTED, out)
        if n:
            counts[name] = n
    return SanitizeResult(out, counts)
