"""Pytest wiring: AD-6 network sandbox for EVERY core-package test suite.

Core packages (packages/* except packages/adapters/*) run with sockets blocked.
Adapter suites and edge tests are exempt (their own tests still must not touch
the network — they use MockTransport — but they are allowed to declare network
dependencies).

Marker-level escape: a core test may request network explicitly with
``@pytest.mark.allow_network`` and a docstring reason; the marker is counted in
the guards README. Default for core = sandboxed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.guards.network_sandbox import enable_sandbox

_REPO = Path(__file__).resolve().parent


def _is_adapter_test(path: Path) -> bool:
    try:
        # resolve() defuses symlink prefixes (/var vs /private/var on macOS)
        rel = path.resolve().relative_to((_REPO / "packages").resolve())
        return rel.parts[0] == "adapters"
    except ValueError:
        return True  # non-package tests (top tests/): not core-code suites → exempt. The guards' own proof tests carry their own sandboxing.


@pytest.fixture(autouse=True)
def _ad6_sandbox(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    if "allow_network" in request.keywords:
        yield
        return
    fspath = Path(str(request.node.fspath))
    if _is_adapter_test(fspath):
        yield
        return
    enable_sandbox(monkeypatch)
    yield
