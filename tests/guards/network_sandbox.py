"""Network sandbox for core-package suites (AD-6 runtime half).

Adapters are exempt by marker/path. Proof tests live in test_network_sandbox.py.
"""

from __future__ import annotations

import socket

import pytest

BLOCKED_MSG = "LI-CI-004: network access in a core-package test (AD-6)"


class _SandboxedSocket:
    def __init__(self, *a, **k):
        raise AssertionError(BLOCKED_MSG)


def enable_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "socket", _SandboxedSocket)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError(BLOCKED_MSG)),
    )
