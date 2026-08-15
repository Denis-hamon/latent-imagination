# Architecture

Monorepo with one **pipeline stage per package**; runtime network access is
illegal outside `packages/adapters/*`. Invariants are governed by the
ARCHITECTURE-SPINE (external BMAD planning workspace); the durable in-repo
copies of the rules are `docs/conventions.md` (drift law) + `tests/guards/`
(mechanical enforcement).

## The invariants (AD-1..AD-14, condensed)

| AD | Rule | Enforced by |
|---|---|---|
| AD-1 | Core never imports adapters; the gate reads ONLY pinned snapshot hand-offs | `tests/guards/imports_lint.py` (AST graph) |
| AD-3 | Stores are append-only; corrections are new hash-linked versions | `store/emit.py` LI-STORE-004/008, `store/validate.py` |
| AD-4 | One artifact type = one owning stage; the gate never writes canonical stores | `tests/guards/writer_inventory.py` (marker scan, table derived from `store.emit.WRITERS` — single source of truth) |
| AD-5 | Chain topology is FIXED: release → bundle → snapshot → ruleset → code_commit; hash-linked + externally time-anchored; no mutable names | `prereg.chain.assemble_chain` (the only builder) |
| AD-6 | No network clients in core packages (adapters exemption) | `tests/guards/network_deps.py` (static) + `network_sandbox.py` (runtime socket block) |
| AD-7 | Two artifact classes: reproducible (content-only: no clock/uuid in hashes) vs occurrence (timestamps allowed) | `store/layout.py REPRODUCIBLE_CLASSES`, emit checks, `determinism_replay` guard |
| AD-8 | store-validate verifies manifest + layout + append-only + prereg precedence | `store/validate.py`, `tests/guards/test_prereg_precedence.py` |
| AD-9 | `prereg` is a PURE governance lib (stdlib only, zero project imports); OTS network lives in the `ots-anchor` adapter edge | package deps + guard |
| AD-12 | Measurement identity = content sha256 (full 64-hex in fields; `[:16]` file names, `[:12]` display only) | `core_schema/identity.py` |
| AD-13 | Derived artifacts carry an `inputs` block; publication refuses to sign on mismatch | `store/emit.py` LI-STORE-003, `publication.release.verify_inputs` |
| AD-14 | Gate packages carry no LLM-client dependencies | `tests/guards/dependency_scan_gate.py` |

## Package topology

```
                       ┌──────────── core-schema (domain types, identity, events) ───────────┐
                       │                        ▲            ▲            ▲                   │
traces-ingest ──► store ◄── labeling ──► harness ◄─ probe ──► publication ─► prereg (pure)   │
   (ingest)     (emit/      (rules v1,   (ERBVE,     (arms,      (release       (chain,       │
                validate)    runner)      figures,    verdict)    assembly)      ledger,       │
                                          delta)                                 certificates) │
                       gate ◄──────────────────────────────────────────────────────┘          │
              (ports, intercept advisory, blocking seam,                                       │
               workload check, shadow)                                                         │
                       ▲                                                                       │
             gate-adapters (claude-code hook, MCP gateway, telemetry ETL, workload/shadow CLI) │
                                                                                               │
   tools-ranking (N≥2 ranking)        corpus (noisy/clean tiers)        latent-gate (RESEARCH — GHOST world model; isolated)
```

Dependency rule: arrows point at importers; `gate` depends only on
core-schema + prereg; `publication` orchestrates adapters; `latent-gate`
(torch/transformers) is a research surface with no import links to the gate family.

| Package | Module | Owns (writer stage) |
|---|---|---|
| li-core-schema | core_schema | domain models: Task, CandidatePatch, ExecutionAttempt, Label (outcome enum), QuarantineRecord, RunRecord, StoreEvent envelope; identity (attempt_id = sha256 of canonical inputs); typed errors `LI-SCHEMA-nnn` |
| li-store | store | store-layout-v1 contract: `emit.write_artifact` (WRITERS table = single source), `validate_store`, `compute_store_version`, DuckDB views (convenience only) |
| li-traces-ingest | traces_ingest | sanitize/normalize → canonical-snapshot rows |
| li-labeling | labeling | rules_v1 (deterministic judge-free classifier), runner (writes labels/quarantine + ledger run rows) |
| li-harness | harness | ERBVE metrics, figures, replay bundles, Act II delta pipeline |
| li-probe | probe | probe arms (baseline LogReg, JEPA), verdict engine, baseline_export (predictor artifact); `[ml]` extra isolates sklearn/torch |
| li-prereg | prereg | PURE lib: AD-5 chain assembly, ledger (`anchor_entry`, `run_entry`, `certificate_entry`), anchor format, offline byte verification, threshold certificates (assemble/verify/supersession/`currently_valid`) |
| li-publication | publication | Act I/Act II release packet assembly; `verify_inputs` (AD-13 fail-closed) |
| li-gate | gate | read port (pinned snapshot, LI-GATE-001..009), advisory `annotate`/`refuse`, blocking seam (`authorize_blocking`, `evaluate_blocking`, `patch_blocked_event`), workload check (`measure_workload_precision`, `authorization_state`), shadow (`select_for_shadow`, `compute_sm_c1`), decision log (append-only, fence LI-GATE-004) |
| li-gate-adapters | gate_adapters | claude_code_hooks (PreToolUse), mcp_gateway (JSON-RPC), telemetry_etl (DuckDB reader), workload check CLI, shadow report CLI |
| li-tools-ranking | tools_ranking | N≥2 candidate ranking, ties explicit, ordering consistency |
| li-corpus | corpus | noisy-tier harvest, exclusion rules, clean tier, versioned corpus artifacts |
| li-latent-gate | latent_gate | GHOST world-model service (MCP stdio + HTTP); RESEARCH surface — isolated from the FR-21 gate |

Adapters (only sanctioned network): `ots-anchor` (OpenTimestamps 0.7.2, the
prereg family's single network hop), `zenodo`, `hf-hub`, `atif-reader`,
`ci-logs`, `harbor-runner`, `public-corpora`.

## Data flow

1. **Ingest** — raw agent/CI traces land in `data/landing/` (adapter deposits,
   occurrence class, gitignored); `traces_ingest` sanitizes + normalizes →
   canonical snapshots in the store.
2. **Label** — `labeling/runner.py` deterministically classifies raw test
   outputs (rules v1, byte-pinned) → labels/quarantine artifacts + ledger run
   rows; prereg precedence guard proves the ruleset was anchored BEFORE its
   decisive run.
3. **Measure** — `harness` computes ERBVE + figures; `probe` trains/evaluates
   arms and renders the verdict mechanically from pre-anchored templates.
4. **Publish** — `publication` assembles release packets; the prereg ceremony
   (AD-5 chain + OTS anchor + ledger + WORM bucket + Zenodo/HF mirrors) signs
   and time-stamps; negative direction (errata/revocations) carries the same
   discipline.
5. **Serve** — the gate consumes a pinned snapshot hand-off (predictor +
   manifest) and annotates the agent's tool-call path (advisory). Blocking
   additionally requires the Epic 7 certificate chain + workload check +
   budget (enforcement OFF until a certificate is issued).

## Governance model (in-repo: `governance/`)

- **prereg-ceremony.md** — freeze → hash → anchor → record; verification is
  offline, third-party, credential-free.
- **probe-design/** — the sealed decision envelope (bar formula, margin,
  strictness, verdict templates) with package hash; Act I verdict: branch iii.
- **gate/** — workload-check protocol + policy TOML, false-block budget
  (seal 51c2ff3f…), shadow-sampling policy, latency budget, OQ closures.
- **certificates/templates/** — branch-specific issuance/superseding templates
  committed before any real issuance (7.1 discipline).
- **act2/** — pins, prerags, pilot phase report (audit trail with addenda),
  arm artifacts, verdict templates.
- **KEYS.md / erratum-protocol.md / anchor-fallback.md** — signer custody,
  hash-linked corrections (never rewrite), OTS→RFC-3161 fallback lane.

## The two strictness regimes (do not unify)

- Probe verdict *crossing*: `precision >= registered_bar` (inclusive) — decision.toml `[strictness]`.
- Blocking authorization + certificate issuance: `precision > registered_bar` (strictly above) — FR-21.

## The two precision surfaces (do not conflate)

- **FR-21 gate** (`li-gate`): certified, hash-pinned, judge-free; advisory
  until a certificate exists; blocking machinery complete but unfired.
- **GHOST research** (`li-latent-gate` + scripts/mcp): latency-energy world
  model with calibrated abstention; advisory-only product; no certificate
  lineage. Shares disciplines (pinned calibration, refuse-to-predict,
  grounded outcomes) but no code.
