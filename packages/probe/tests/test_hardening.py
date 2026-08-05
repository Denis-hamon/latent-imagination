"""Hardening-lite criteria — each rejector function-proven on synthetic fixtures."""

from __future__ import annotations

from probe.hardening import filter_slice, reject_reasons


def _item(
    instance_id="i-1",
    fail_to_pass=None,
    patch="--- a/src/mod.py\n+++ b/src/mod.py\n@@ -1,1 +1,1 @@\n-x\n+y\n",
    **kw,
):
    return {
        "instance_id": instance_id,
        "FAIL_TO_PASS": fail_to_pass or ["pkg/tests/test_mod.py::test_x"],
        "patch": patch,
        **kw,
    }


def test_infra_config_f2p_rejected():
    item = _item(fail_to_pass=["pkg/tests/conftest.py::test_setup"])
    assert "f2p-infra-config" in reject_reasons(item)


def test_test_only_patch_rejected():
    item = _item(patch="--- a/pkg/tests/test_mod.py\n+++ b/pkg/tests/test_mod.py\n@@ -1,1 +1,1 @@\n-x\n+y\n")
    assert "test-only-patch" in reject_reasons(item)


def test_known_weak_match_rejected():
    item = _item(instance_id="django-1234")
    assert "known-weak-suite" in reject_reasons(item, known_hackable={"django-1234"})


def test_clean_item_survives():
    kept, rejected = filter_slice([_item()])
    assert len(kept) == 1 and not rejected


def test_reject_rate_visibility(tmp_path):
    items = [
        _item("ok-1"),
        _item("bad-1", fail_to_pass=[".github/workflows/ci.yml::check"]),
        _item("bad-2", patch="--- a/t/test_x.py\n+++ b/t/test_x.py\n@@ -1,1 +1,1 @@\n-a\n+b\n"),
    ]
    kept, rejected = filter_slice(items)
    assert len(kept) == 1
    assert {r.instance_id for r in rejected} == {"bad-1", "bad-2"}
