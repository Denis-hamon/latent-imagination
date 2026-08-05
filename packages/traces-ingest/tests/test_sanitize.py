"""Sanitizer tests — prove the function on synthetic secrets."""

from __future__ import annotations

from traces_ingest.sanitize import sanitize_text


def test_redacts_known_secret_classes():
    text = "aws key AKIAIOSFODNN7EXAMPLE and email bob@corp.io and token: 'abcdef0123456789zzzz' and key sk-ant_API03-xyzXYZ0123456789012345678901234567890"
    res = sanitize_text(text)
    assert res.counts.get("aws_access_key") == 1
    assert res.counts.get("email") == 1
    assert res.counts.get("generic_assignment_token") >= 1
    assert res.counts.get("openai_key") == 1
    assert "AKIAIOSFODNN7EXAMPLE" not in res.text
    assert "bob@corp.io" not in res.text
    assert "sk-ant" not in res.text
    assert res.total >= 4


def test_clean_text_passes_untouched():
    res = sanitize_text("all good here, no tokens")
    assert res.total == 0
    assert res.text == "all good here, no tokens"


def test_pem_block_redacted():
    res = sanitize_text("-----BEGIN RSA PRIVATE KEY-----\nMII…\n-----END RSA PRIVATE KEY-----")
    assert res.counts.get("private_key_block") == 1
