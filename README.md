# Ghost

**The world model for code changes.** Ghost predicts whether a patch will pass
its tests — before anyone runs them — and says so with calibrated
probabilities, or refuses to answer when it cannot back the number.

Ghost plugs into any coding agent (Claude Code, Codex, Cursor, OpenHands…)
as an MCP server. The agent proposes K candidate patches; Ghost tells it which
futures are worth betting on, which tests to actually run, and which candidate
to ship — with evidence, risks, and explicit uncertainty.

> Not another copilot. The decision layer your agents don't have yet.

```
agent generates K patches ──> Ghost compares their futures
                                  │
                     ┌────────────┴────────────┐
                     │ not enough evidence      │ ≥ 8 grounded test runs
                     │ → execution plan         │ → conformal calibration
                     │ → NO recommendation      │ → recommendation + risks
                     └─────────────────────────┘
```

## What you get

| Tool | What it does |
|---|---|
| `compare_patches` | Ranks K candidate patches for one problem. Phase 1 returns the minimal set of tests to run first; Phase 2 (≥ 8 real outcomes) returns a calibrated recommendation with per-candidate probabilities and abstentions. Optional `declared_tests`: per-test P(still failing) column (signal, never a verdict; abstains when absent). |
| `risk_scan` | Scores a single draft patch against the geometry of past grounded outcomes. Verdicts only in the calibrated regime; named abstention everywhere else. |
| `near_mis_patches` | The k nearest past patches with their **actual** execution outcomes — evidence, not vibes. |
| `preflight_patch` | Free deterministic checks (does it apply? does it parse?) before spending a single token. |
| `report_outcome` | Feeds the pool. Only grounded outcomes are accepted (`tests-run`, `ci`, `human`) — model opinions are rejected by contract. |

```bash
claude mcp add --transport http ghost http://<host>:8093/mcp
# or in mcpServers: {"ghost": {"url": "http://<host>:8093/mcp"}}
```

## Numbers, as served today

- **Served pool v12 — 430 grounded rows** (205 successes / 225 failures),
  encoder `jina-embeddings-v2-code`, geometry learned from patch embeddings;
- **Conformal Mondrian calibration**: 7 strata with per-family error
  guarantees ≤ 10 %, including the first TypeScript strata
  (`compression/lite`, `usage-tracking`, `cache-affinity`); realized error on
  hold-outs 9.1 % ≤ 10 % guaranteed;
- **TypeScript signal, certifiable population (211 rows)**: ext-LOAO AUC
  **0.708**, CI95 [0.635, 0.775]; encoder ablation under sealed grids:
  jina 0.743 vs unixcoder 0.695 — the representation arm crossed its
  pre-registered gate before any pool migration;
- **Data pipeline**: 60 real bug-fix tickets mined from OSS git history
  (buggy state = parent of the actual fix commit; labels = the project's own
  regression tests, executed — never predicted).

Everything above is re-derivable from this repository: pre-registered
hypotheses, sealed decision grids, append-only measurement ledger, OTS-anchored
proofs. See `governance/`.

## The doctrine (why you can trust the numbers)

1. **No outcome is ever guessed.** A label exists only when tests actually
   ran (`grounded_by`). The pool refuses model opinions.
2. **Abstention is a feature.** Below the evidence bar (8 grounded runs per
   session, 12 rows per stratum), Ghost returns an execution plan or a named
   non-coverage — never a confident shrug.
3. **Every experiment is pre-registered.** Grids, populations, and decision
   rules are anchored (sha256 + OpenTimestamps) *before* measurement;
   amendments are append-only and disclosed.
4. **Serving is reversible.** Pool, calibration, and encoder form one
   atomic drop-in; rollback is a config swap, drilled.

## Repository

- `packages/` — pipeline stages (batch core, zero network at runtime)
- `scripts/mcp/` — the served MCP server (`ghost_server.py`, v0.8.1) + HTTP transport
- `scripts/futures/` — session bootstrap & local calibration (the
  `compare_patches` engine, usable standalone)
- `scripts/act2/` — measurement windows: quotas, probes, label chains,
  pool promotions (v6 → v12)
- `governance/` — pre-registrations, sealed grids, promotion gates, proofs
- `data/registries/` — source registry (licenses, usage rights, snapshots)
- `docs/` — architecture, data models, API contracts

## Quickstart (from a cold clone)

```bash
# uv 0.12.1 recommended; Python 3.14.6 via .python-version
uv sync --locked --all-packages
uv run ruff check .
uv run pytest -q          # 635 tests, deterministic, no network
```

## License

Apache-2.0.
