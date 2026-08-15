# Project Documentation Index

Generated 2026-08-15 · target repo: `latent-imagination` · mode: initial_scan · scan level: deep

## Project Overview

- **Type:** monorepo (uv workspace; one pipeline stage per package; research surface isolated)
- **Primary Language:** Python >= 3.14 (pinned 3.14.6)
- **Architecture:** content-addressed measurement pipeline + governance envelope (AD-1..AD-14 invariants)

## Quick Reference

- **Tech Stack:** Python 3.14, uv 0.12.1, pytest 9.1.1, ruff 0.16.1, pydantic 2.13.4, duckdb/pyarrow, opentimestamps-client 0.7.2 (adapter), torch/transformers (research packages only)
- **Entry Points:** `li-gate-hook-claude` (advisory wire) · `python -m gate_adapters.*` (deployer CLIs) · `scripts/prereg/*` (ceremonies) · `scripts/mcp/ghost_http_server.py` (GHOST MCP :8093) · `demo/*/run_demo.py`
- **Architecture Pattern:** pure-library stages over a content-addressed append-only store, sealed governance envelope, ceremony-signed releases

## Generated Documentation

- [Project Overview](./project-overview.md)
- [Architecture](./architecture.md)
- [Source Tree Analysis](./source-tree-analysis.md)
- [Data Models](./data-models.md)
- [API Contracts](./api-contracts.md)
- [Development Guide](./development-guide.md)

## Existing Documentation (repo-local)

- [docs/conventions.md](./conventions.md) — binding daily-drift conventions (spine upstream wins on conflict)
- [docs/field-pilot-setup.md](./field-pilot-setup.md) — 15-minute "Kenji" advisory-gate deployment guide
- [docs/world-model-mcp-design.md](./world-model-mcp-design.md) — GHOST MCP design doc + measured results (living)
- [docs/world-model-of-software-e4.md](./world-model-of-software-e4.md) — paper draft "A World Model of Software, Measured"
- [docs/literature-synthesis-code-wm.md](./literature-synthesis-code-wm.md) / [literature-synthesis-wmm.md](./literature-synthesis-wmm.md) — literature waves 1 & 2
- [README.md](../README.md) — public pitch, commands, contract pointers
- [governance/README.md](../governance/README.md) — ceremonies, key custody, prerigistration index
- [packages/store/store-layout-v1/README.md](../packages/store/store-layout-v1/README.md) — the store contract (authoritative)
- [tests/README.md](../tests/README.md) — guard semantics table

## External (BMAD planning workspace — outside this repo)

- PRD (FR-1..FR-26): `../_bmad-output/planning-artifacts/prds/prd-wo-2026-08-05/prd.md`
- ARCHITECTURE-SPINE (AD-1..AD-14): `../_bmad-output/planning-artifacts/architecture/architecture-wo-2026-08-05/`
- Sprint status + story records: `../_bmad-output/implementation-artifacts/sprint-status.yaml`

## Getting Started

```sh
uv sync --locked --all-packages
uv run ruff check .
uv run pytest -q --ignore=scripts/act2/test_pilot_harness.py   # see development-guide.md caveats
```

For AI-assisted development on this repo, load in order: this index →
[architecture.md](./architecture.md) → the module you're touching →
[development-guide.md](./development-guide.md) (guards section) →
[api-contracts.md](./api-contracts.md) if you touch a seam.
