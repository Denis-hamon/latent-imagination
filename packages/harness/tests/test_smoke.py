"""Smoke test: import works AND resolves to this package's src (AD shadow-safety)."""

from pathlib import Path


def test_imports():
    import harness

    origin = Path(getattr(harness, "__file__", None) or "")
    expected = Path(__file__).resolve().parents[1] / "src"
    assert origin != Path(""), "namespace-package shadowing detected (no __file__)"
    assert expected in origin.parents, (
        f"module resolved from {origin}, expected under {expected}"
    )
