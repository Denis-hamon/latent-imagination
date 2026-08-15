# Source Tree Analysis

Annotated top-level structure. Bulk data is deliberately NOT in-repo
(see data/README.md: "Small, committed. Bulk artifacts live on OVH Object
Storage and are referenced by content hash").

```text
latent-imagination/
├── README.md                      # public pitch + commands + contract pointers (external BMAD workspace)
├── LICENSE                        # Apache-2.0
├── pyproject.toml                 # uv workspace root (package = false); dev deps: pytest 9.1.1, ruff 0.16.1
├── uv.lock                        # 104 packages resolved; 21 workspace members
├── .python-version / .tool-versions  # Python 3.14.6 / uv 0.12.1 (mirrored in CI pins)
│
├── packages/                      # ONE PIPELINE STAGE PER PACKAGE (zero runtime network, AD-6)
│   ├── core-schema/               # domain types + identity + events + typed errors (pydantic)
│   ├── store/                     # store-layout-v1 contract: emit/validate/version/registry/views
│   │   └── store-layout-v1/README.md   # THE layout contract ("this document IS the contract")
│   ├── traces-ingest/             # sanitize/normalize → canonical snapshots
│   ├── labeling/                  # rules v1 (judge-free) + runner + replay-identical discipline
│   ├── prereg/                    # PURE governance lib (AD-9): chain, ledger, verify, certificates
│   ├── harness/                   # ERBVE metrics, figures, replay bundles, Act II delta
│   ├── probe/                     # arms (baseline/JEPA), verdict engine, predictor export ([ml] extra)
│   ├── publication/               # release packet assembly, AD-13 verify_inputs
│   ├── corpus/                    # noisy/clean tiers, exclusion rules, versioned corpus
│   ├── gate/                      # FR-21 gate: ports (pinned), intercept (advisory), blocking seam,
│   │                              #   workload check, shadow sampling, decision log
│   ├── gate-adapters/             # claude-code hook, MCP gateway, telemetry ETL, check CLIs
│   ├── tools-ranking/             # N≥2 ranking, ties explicit
│   ├── latent-gate/               # GHOST research service (MCP/HTTP; isolated from the FR-21 gate)
│   │   └── public/                # served artifacts: model.json, eval-pack, demo pages
│   ├── adapters/                  # ★ ONLY sanctioned network deps (7 adapters)
│   │   ├── ots-anchor/            #   OpenTimestamps 0.7.2 — prereg family's single network hop
│   │   ├── zenodo/  ├── hf-hub/   #   distribution edges (disclosed skips when tokens absent)
│   │   ├── atif-reader/  ├── ci-logs/  ├── harbor-runner/  └── public-corpora/
│   └── (each package: pyproject.toml, src/<module>/, tests/, README)
│
├── scripts/                       # orchestration surfaces (writer-guard scans scripts/**;
│   │                              #   sanctioned write surfaces: prereg/ act1/ probe/ act2/)
│   ├── prereg/                    # ceremonies: ceremony.sh, release_ceremony.py,
│   │                              #   certificate_rehearsal.py (7.1), certificate_ceremony.py (7.5)
│   ├── publication/               # release_act2.py (Act II driver, reuses Act I ceremony)
│   ├── act1/                      # campaign.py, sim_campaign.py, live_agent.py, dry-run.sh
│   ├── act2/                      # ~50 pilot scripts: s1..s14 series, e1..e6 studies, RCT,
│   │                              #   pool builders, flywheel (mcp_flywheel.py), calibrations
│   ├── mcp/                       # GHOST MCP: ghost_server.py (stdio) + ghost_http_server.py (HTTP 8093)
│   ├── corpus/ probe/ gate/ ranking/   # thin drivers over package logic
│   └── setup-node.sh              # idempotent GPU-node provisioning (AD-10 spec)
│
├── governance/                    # PRE-REGISTERED DECISIONS, ceremonies, keys, protocols
│   ├── prereg-ceremony.md  KEYS.md  erratum-protocol.md  anchor-fallback.md
│   ├── certificates/templates/    # issued.md / superseding.md (committed BEFORE first issuance)
│   ├── gate/                      # workload-check protocol+policy, false-block budget (seal 51c2ff3f…),
│   │                              #   shadow-sampling policy+doc, latency budget, OQ closures, measurements
│   ├── probe-design/              # sealed envelope: design/decision TOML, package manifest, runs/, verdict-templates/
│   ├── act1-design/  act2/        # frozen designs, campaign pins/prerags/reports, arm-artifacts, verdict templates
│   ├── corpus/  ranking/  ovh/  public-measurement/
│   └── figures-taxonomy.toml  flaky-policy.toml  sanitize-policy.toml  labeling-decision-tree.md
│
├── data/
│   ├── README.md
│   ├── registries/sources.yaml    # FR-1 trace-source registry (seed entries + real CI-logs source)
│   ├── release-store/             # COMMITTED: ledgers (prereg-ledger.jsonl), chains/ (8), proofs/ (9, incl. live OTS)
│   ├── landing/                   # GITIGNORED bulk: act2-pilot pools/logs/results, swe-bench/swe-smith corpora
│   └── store/                     # GITIGNORED bulk parquet (AD-10 manifest-in-repo)
│
├── docs/                          # repo-local documentation (this tree) + design/literature docs
├── demo/
│   ├── gate-advisory/             # public demo #1: PreToolUse wire on SWE-bench Verified (5.5)
│   └── gate-mcp/                  # public demo #2: MCP wire on gpt-4o trajectories (8.4, FR-25 distinctness)
├── bench/                         # Phoenix read-only analysis mirror (docker compose; never canonical)
├── act2-pilot-archive/            # pre-landing vestige: 4 buggy/healthy source pairs of the first pilot
├── tests/
│   ├── README.md                  # guard semantics table ("green" meaning + add-a-guard rules)
│   ├── guards/                    # 7 guards + extras_isolation; each mutation-proven, LI-CI-00n coded
│   ├── e2e/                       # ceremony rehearsals, demos bit-rot tripwires, ranking conformance
│   └── test_bench_feed.py  test_campaign.py  test_e2e_stranger_reproduces_storefigure.py
└── .github/workflows/ci.yml       # guard job (sync+lint+test) + replay-check job (clean-host replay proof)
```

## Entry points

| Entry point | What it starts |
|---|---|
| `packages/gate-adapters` console script `li-gate-hook-claude` | Claude Code PreToolUse hook (advisory wire) |
| `python -m gate_adapters.telemetry_etl` / `workload_check` / `shadow_report` | deployer-local CLIs (5.6 invocation parity) |
| `scripts/prereg/ceremony.sh <chain_hash>` | live OTS anchoring ceremony step |
| `scripts/prereg/{release_ceremony,certificate_rehearsal,certificate_ceremony}.py` | release + certificate ceremony machinery |
| `scripts/mcp/ghost_{server,http_server}.py` | GHOST MCP (stdio / HTTP 8093) |
| `demo/*/run_demo.py` | public demos (regenerate record/ from scratch) |

## Integration seams between surfaces

- **prereg → everything**: hashing/chain/ledger library imported by labeling
  (precedence), publication (signing), gate (certificates). Never network.
- **gate → deployments**: pinned snapshot hand-off (META.json + predictor.json /
  certificate.json + supersession-manifest.json) + decisions.jsonl log (fence:
  never under a store root, LI-GATE-004).
- **store → readers**: layout README is the contract; DuckDB views are
  convenience-never-obligation (AD-8).
- **GHOST (latent-gate/scripts/mcp) → agents**: MCP tools over HTTP/stdio;
  grounded-outcome contract (`report_outcome` with `grounded_by`) feeds the
  nightly flywheel (`scripts/act2/mcp_flywheel.py` → pool promotion).
