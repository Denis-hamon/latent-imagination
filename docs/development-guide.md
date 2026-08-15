# Development Guide

## Prerequisites (pinned — do not drift)

| Tool | Version | Where pinned |
|---|---|---|
| Python | 3.14.6 | `.python-version`, `.tool-versions` |
| uv | 0.12.1 | `.tool-versions`, CI `astral-sh/setup-uv` SHA-pin |
| pytest | 9.1.1 | root `pyproject.toml` dev group |
| ruff | 0.16.1 | root `pyproject.toml` dev group (target py314) |

## Setup

```sh
uv sync --locked --all-packages        # all 20 workspace members + root
```

The default environment is **sklearn/torch-free by design** (story 3.7
extras-isolation: probe trains with `probe[ml]`, the advisory serve path needs
nothing beyond stdlib). To exercise the ML extra:
`uv sync --locked --all-packages -P probe --extra ml`.

## Daily commands

```sh
uv run ruff check .                    # lint (CI-parity)
uv run pytest -q                       # full suite incl. guards + smoke + e2e (green: 532 passed, 6 skipped)
uv run pytest packages/gate -q         # targeted package
uv run pytest tests/guards -q          # the 7 AD-enforcing guards
```

Known environment caveats (by design, not regressions):
- The default env is **sklearn/torch-free** (story 3.7 extras-isolation). The 3
  `probe` baseline tests and 1 `gate` predict test SKIP via `find_spec` /
  `importorskip`. To run them: `uv sync --locked --all-packages -P probe --extra ml`.
- Live-anchor tests are opt-in: `LI_OTS_LIVE=1` (OTS calendars network test).

## Conventions (binding — `docs/conventions.md` + spine)

- One pipeline stage per package; packages kebab-case (`li-*` dists), modules snake_case.
- Errors: typed `LI-<PKG>-nnn`, serialize `{code, message, ctx}`. Allocated ranges:
  SCHEMA 001-006 · STORE 001-008 · GATE 001-009 · GADPT 001-006 · PUB 001-030 ·
  LABEL 001-002 · HARNESS 020 · PRERE 001-006 · CI 001-00n · REGISTRY 002-004.
- Timestamps ISO-8601 UTC `Z`; content-hash identity (AD-12); reproducible
  artifacts content-only (AD-7); config TOML committed, env prefix `LI_`.
- Event kinds: past-tense snake_case with ≥1 underscore.
- Dependencies: exact pin + one-line rationale; NO network clients in core (AD-6).
- Commit hygiene: **one story = one commit, explicit paths, never `git add -A`**.
- Domain terms verbatim from the PRD glossary (ERBVE, Flip, Candidate Patch,
  Net-Positive Precision Bar, Threshold Certificate, Advisory/Blocking Mode…).

## Writing code against the guards

The guard suite (`tests/guards/`) enforces invariants MECHANICALLY — a new guard
must include a mutation fixture proving its function and a row in
`tests/README.md`:

- **writer_inventory**: don't add store-write markers (`write_artifact(`,
  `write_text(`, `write_bytes(`, …) to non-owning packages or non-sanctioned
  script surfaces (sanctioned: `scripts/{prereg,act1,probe,act2}`). Pattern used by
  sanctioned deployer-local writers: plain `open().write()` (decision_log precedent).
- **imports_lint / network_deps / network_sandbox**: core never imports adapters;
  adapters are the only network surface.
- **dependency_scan_gate**: gate packages carry no LLM client deps.
- **prereg_precedence**: label manifests must link a run whose ruleset anchored first.

## Testing strategy

- Per-package `tests/` + top-level `tests/` for e2e, determinism replays, guards.
- Hermetic fixtures in `tmp_path` ONLY — never the real `data/store` or
  `data/release-store` (Epic 3 lesson).
- The conftest AD-6 socket sandbox auto-blocks network in `packages/*` tests
  (adapters exempt); a test needing sockets is a bug.
- Live-anchor opt-in: `LI_OTS_LIVE=1`; the committed `proofs/3ff03b8a….ots` is
  parsed byte-for-byte by offline tests (digest = sha256(raw chain bytes)).
- Determinism replays assert byte-identical re-runs (AD-7).
- Fail-closed loaders: no optional inputs ("an optional pin is not a pin"),
  strict-bool numerics, NaN/Inf guarded, one-buffer read (no TOCTOU).

## CI/CD

`.github/workflows/ci.yml` (2 jobs, SHA-pinned actions, weekly dependabot):
1. **guard**: sync → ruff → full pytest.
2. **replay-check**: replays a Tier-1 bundle on a CLEAN runner (story 1.11 AC3 —
   reproducibility proved off the developer's machine).

Releases: public GitHub repo `Denis-hamon/latent-imagination`; Zenodo DOI +
HF Hub mirror via ceremony adapters (disclosed skips when tokens absent).

## Ops

- GPU node provisioning: `scripts/setup-node.sh` (idempotent; spec in `governance/ovh/`).
- GHOST MCP service: systemd on the node, `scripts/mcp/README.md` (client config,
  4-step contract preflight→risk_scan→tests→report_outcome).
- Phoenix bench mirror: `bench/docker-compose.yml` (read-only, never canonical).
