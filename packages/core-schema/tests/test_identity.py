"""Canonical identity contract (AD-12): stability, order-invariance, window semantics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from core_schema.domain import EnvironmentFingerprint, Task
from core_schema.identity import attempt_id, fingerprint_hash, task_fingerprint

AWARE = datetime(2026, 8, 5, 10, 0, 0, tzinfo=UTC)
DIFF = "diff --git a/x.py b/x.py\r\n--- a/x.py\r\n+++ b/x.py\r\n@@ -1 +1 @@\r\n-old\r\n+new\r\n"


def make_fp(**overrides) -> EnvironmentFingerprint:
    base = {"os_family": "linux", "python_version": "3.12.8", "deps_lock_sha256": "a" * 64}
    base.update(overrides)
    return EnvironmentFingerprint(**base)


class TestTaskFingerprint:
    def test_key_order_irrelevant(self):
        h1 = task_fingerprint("django/django", "c" * 40, ("t1", "t2"))
        h2 = task_fingerprint("django/django", "c" * 40, ("t2", "t1"))
        assert h1 == h2

    def test_matches_task_model(self):
        t = Task.from_parts("django/django", "c" * 40, ("t2", "t1"))
        assert t.task_id == task_fingerprint("django/django", "c" * 40, ("t2", "t1"))


class TestAttemptId:
    def test_two_sources_same_logical_attempt_same_id(self):
        fp = make_fp()
        a = attempt_id("t" * 64, DIFF, fp, AWARE)  # "source A" reading
        b = attempt_id("t" * 64, DIFF, fp, AWARE)  # "source B" reading
        assert a == b
        assert len(a) == 64  # sha256 hex

    def test_crlf_trailing_ws_variance_same_id(self):
        fp = make_fp()
        a = attempt_id("t" * 64, DIFF, fp, AWARE)
        b = attempt_id("t" * 64, DIFF.replace("\r\n", "\n") + "   \n\n", fp, AWARE)
        assert a == b

    def test_window_minute_difference_different_id(self):
        fp = make_fp()
        a = attempt_id("t" * 64, DIFF, fp, AWARE)
        b = attempt_id("t" * 64, DIFF, fp, AWARE + timedelta(minutes=1))
        assert a != b

    def test_naive_start_rejected(self):
        import pytest
        from core_schema.errors import SchemaError

        with pytest.raises(SchemaError) as exc:
            attempt_id("t" * 64, DIFF, make_fp(), datetime(2026, 8, 5, 10))  # noqa: DTZ001 - naive is the tested rejection path
        assert exc.value.code == "LI-SCHEMA-002"

    def test_aware_paris_equals_utc_instant(self):
        fp = make_fp()
        paris = timezone(timedelta(hours=2))
        a = attempt_id("t" * 64, DIFF, fp, AWARE)
        b = attempt_id("t" * 64, DIFF, fp, datetime(2026, 8, 5, 12, 0, 0, tzinfo=paris))
        assert a == b  # same instant, normalized to UTC

    def test_fingerprint_field_order_irrelevant(self):
        # Built twice with kwargs in different orders -> identical hash
        class FP1(EnvironmentFingerprint):
            pass

        x = FP1(os_family="linux", python_version="3.12.8", deps_lock_sha256="a" * 64)
        y = make_fp()
        assert fingerprint_hash(x) == fingerprint_hash(y)
