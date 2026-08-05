"""Sanitizer — secrets/PII redaction with counts, fail-closed (FR-2).

Pattern policy is FROZEN (governance/sanitize-policy.toml): editing it is a
pre-registered change event. Behavior contract:
- hits are REDACTED (the redacted text, never the raw text, flows downstream)
- any hit in a field destined to canonical storage is REPORTED with counts of
  per class; a record carrying hits must be flagged ``sanitized=True`` so the
  measurement can disclose its sanitized share
- there is no silent-drop path and no adjudicate-by-judgment path.
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
    """Apply the frozen patterns on RAW text (call before any serialization —
    sanitizing a JSON dump would let escaped quotes defeat the quote-optional
    token patterns)."""
    counts: dict[str, int] = {}
    out = text
    for name, pattern in PATTERNS.items():
        out, n = re.subn(pattern, REDACTED, out)
        if n:
            counts[name] = n
    return SanitizeResult(out, counts)
