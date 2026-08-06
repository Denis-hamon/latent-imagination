# Latent Imagination

Patch-consequence prediction for coding agents, computed in representation space — an open measurement instrument (false-start rate / ERBVE) first, then a feasibility probe, then an advisory interceptor gate on the agent tool-call path. Judge-free validity: every claim is owned by each task's own fail-to-pass tests and reproducible by a third party in one sitting.

> License: **Apache-2.0**. This repository is now cleared for public release.

## Quickstart (from a cold clone)

```bash
# uv 0.12.1 recommended (CI pins it via astral-sh/setup-uv);
# Python 3.14.6 comes from .python-version — uv downloads it automatically.
uv sync --locked --all-packages
uv run ruff check .
uv run pytest -q
```

## Layout

- `packages/` — one pipe stage per package (batch core, zero network at run time)
- `packages/adapters/` — edge adapters; the only place network deps are allowed
- `governance/` — pre-registration & key custody docs
- `bench/` — Phoenix analysis bench (read-only mirror)
- `data/` — registries, manifests, replay bundles (small, committed)
- `tests/` — e2e, determinism replays, CI guard suite
- `docs/conventions.md` — the binding consistency conventions

## Contract

The WHAT lives in the PRD (FR-1..FR-26), the invariant HOW in the architecture spine (AD-1..AD-14). Both are workspace documents; contradicting an AD requires a spine revision, not a workaround.

Planning artifacts: `../_bmad-output/planning-artifacts/` (PRD, spine, epics). Sprint status: `../_bmad-output/implementation-artifacts/sprint-status.yaml`.
