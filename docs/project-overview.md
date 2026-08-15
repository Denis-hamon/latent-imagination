# Latent Imagination — Project Overview

**Patch-consequence prediction for coding agents, computed in representation space.**

An open measurement instrument first (judge-free false-start metrics), then a
feasibility probe, then an advisory gate on the coding-agent tool-call path.
Core doctrine: every validity claim belongs to a task's fail-to-pass tests and
must be reproducible by a third party "in one sitting" — no LLM judge anywhere
in the labeling path (FR-3, FR-9).

- **Status**: cleared for public release (v0.1.0 branch-iii measurement published;
  Epic 7 FR-21 blocking-mode machinery landed 2026-08-15, enforcement OFF by design)
- **License**: Apache-2.0
- **Repository type**: monorepo — uv workspace, one pipeline stage per package
- **Primary language**: Python 3.14 (strict pins: uv 0.12.1, pytest 9.1.1, ruff 0.16.1)

## What it is

1. **Measurement instrument** — ERBVE (Execution-Runs-Before-Valid-Execution)
   false-start metrics over labeled execution traces, judge-free
   (`labeling/rules_v1.py`).
2. **Probe** — does representation-space structure carry signal about patch
   outcomes? Act I verdict: branch (iii), no arm crossed the registered
   net-positive precision bar 0.8889 (published measurement-only result).
3. **Gate** — an advisory interceptor on the agent tool-call path
   (FR-18/FR-19): predicts flip probability, annotates, never halts.
   Blocking Mode (FR-21/FR-22) is fully machined (Epic 7) but cannot engage
   without a certificate issued from a crossing-bar verdict.
4. **GHOST MCP** — a world-model research service (scripts/mcp): goal-free
   patch-risk scoring over a labeled pool with calibrated abstention
   (acc 0.952 on its 10% coverage regime, LOAO). Advisory only.

## Quick reference

| Category | Technology | Version |
|---|---|---|
| Language | Python | >= 3.14 (pinned 3.14.6) |
| Workspace/build | uv | 0.12.1 |
| Test | pytest | 9.1.1 |
| Lint | ruff | 0.16.1 (target py314) |
| Schema | pydantic | 2.13.4 (core-schema/store/gate-adapters only) |
| ML (research surface) | torch + transformers (unixcoder-base) | latent-gate / probe[ml] extra only |
| Analytics | duckdb / pyarrow | telemetry ETL + store views |
| Anchoring | opentimestamps-client | 0.7.2 (adapter only) |
| Distribution | Zenodo + HF Hub adapters | httpx 0.28.1 / huggingface_hub 1.26.1 |

## Documentation map

- [Architecture](./architecture.md) — invariants (AD-1..AD-14), package topology, data flow
- [Source tree analysis](./source-tree-analysis.md) — annotated directories
- [Data models](./data-models.md) — domain schema, store layout, ledger/artifact formats
- [API contracts](./api-contracts.md) — gate seams, GHOST MCP tools, ceremony CLIs
- [Development guide](./development-guide.md) — setup, commands, testing, CI, guards
- Master index: [index.md](./index.md)

## External contract pointers

The normative WHAT/HOW lives in the BMAD planning workspace OUTSIDE this repo
(`../_bmad-output/planning-artifacts/` — PRD FR-1..FR-26, ARCHITECTURE-SPINE
AD-1..AD-14; sprint + story records in `../_bmad-output/implementation-artifacts/`).
This docs/ tree is the repo-local, self-contained documentation for AI-assisted
work; it cites in-repo artifacts (governance/) wherever possible.
