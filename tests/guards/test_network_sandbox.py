"""Proof: the sandbox actually blocks sockets (function, not presence)."""

from __future__ import annotations

import socket

import pytest

from tests.guards.network_sandbox import enable_sandbox


@pytest.fixture()
def sandboxed(monkeypatch: pytest.MonkeyPatch):
    enable_sandbox(monkeypatch)


def test_sandbox_blocks_tcp(sandboxed):
    with pytest.raises(AssertionError, match="LI-CI-004"):
        socket.create_connection(("example.com", 443), timeout=1)


def test_sandbox_blocks_socket_ctor(sandboxed):
    with pytest.raises(AssertionError, match="LI-CI-004"):
        socket.socket()
