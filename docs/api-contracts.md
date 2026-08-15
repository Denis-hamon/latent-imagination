# API Contracts

Public surfaces of the repo: the gate seams (FR-18/19/21/22), the GHOST MCP
tools (research surface), ceremony CLIs, and adapter wires. All gate-family
refusals speak typed LI-GATE-nnn codes; never silence, always logged.

## Gate read port — `gate/ports.py`

```python
load_pinned_snapshot(root, *, expected_predictor_hash: str) -> PinnedSnapshot
```
- Pin is MANDATORY 64-hex ("an optional pin is not a pin"); fail-closed LI-GATE-001 on: unreadable/unparseable manifests, unknown layout, malformed store_version, hash mismatch, unsupported predictor version, malformed corpus_version.
- One buffer per file: same bytes are parsed AND hashed (no TOCTOU).
- `PinnedSnapshot{root, store_version, predictor_hash, predictor_version, corpus_version, manifest}`.
- `SUPPORTED_PREDICTOR_VERSIONS = ("probe-predictor-v0",)`; `INTERFACE_VERSION = "gate-iface-v1"`.

## Advisory annotation — `gate/intercept.py` (the ONLY candidate-facing behavior)

```python
CandidateCtx(repo, patch_diff, rationale_ptr, wire_payload_sha256=None)  # .patch_sha256 = sha256(RAW diff), computed once
annotate(snapshot, ctx, *, flip_probability, model_family, latency_s, disclosure,
         prediction_target_tier, prediction_target_detail=None, now=None) -> StoreEvent  # kind gate_annotated
refuse(snapshot, ctx, *, reason, now=None) -> StoreEvent                                  # kind prediction_refused (OQ-10 abstain)
timed(fn, *a, **kw) -> (result, seconds)                                                  # NFR-P1 latency instrumentation
```
- `prediction_target_tier ∈ {"diff_touched","user_designated"}` else LI-GATE-002 (abstain instead).
- `_check_number`: strict-bool rejection + NaN/Inf/range guards.
- `_check_disclosure`: measured_precision ∈ [0,1] AND must equal the pinned manifest's measured precision (±1e-9) — disclosure is pinned, never invented.

## Blocking seam — `gate/blocking.py` (the ONLY allowlisted blocking surface)

```python
authorize_blocking(snapshot_root, *, expected_certificate_hash, query_generation=None) -> BlockingAuthorization
  # pin shape → certificate_from_dict (body hash recomputed) → pin match → manifest integrity
  # → currently_valid → generation scope → certified_precision > registered_bar (STRICT)
  # ANY failure → SchemaError LI-GATE-006
refuse_blocking(reason, *, certificate_hint=None, now=None) -> StoreEvent   # kind blocking_refused
load_false_block_budget(path) -> FalseBlockBudget                            # LI-GATE-009, fail-closed, seal = sha256(file bytes)
evaluate_blocking(*, flip_probability, prediction_target_tier, context: BlockContext, now) -> BlockDecision
  # leg order = audit trail: budget present → local_check.blocking_enabled is True
  # → recorded local precision STRICTLY > bar (forged flags refused) → freshness
  # → OQ-10 denominator → flip_probability > threshold (strict); else action="advise" with named reason
patch_blocked_event(candidate_repo, candidate_patch_sha256, *, flip_probability,
                    prediction_target_tier, context, decision, now=None) -> StoreEvent   # kind patch_blocked
  # payload: candidate, prediction{…threshold}, certificate_hash, local_precision_estimate,
  #          registered_bar, cost_accounting{cost_exec_usd, cost_regen_usd,
  #          expected_regen_cost_usd, budget_seal_sha256}, budget{rate, seal}, reason
BlockContext(certificate: BlockingAuthorization, local_check: LocalCheckState,
             budget: FalseBlockBudget | None, max_age_days: int, binarization_threshold: float)
```
- Registry: LI-GATE-006 (authz refusals) · LI-GATE-009 (budget load).
- Confidence scores are never an input anywhere (FR-21).

## Workload check — `gate/workload_check.py`

```python
WorkloadRow  # StrictModel extra="forbid": patch_sha256, flip_probability, prediction_target_tier, outcome
             # — mechanical encoding of "confidence never an input"
wilson95_interval(k, n) -> (lo, hi)          # z=1.96, clamped, n=0 → (0,0); ci_method per decision.toml
measure_workload_precision(rows, *, binarization_threshold=0.5) -> WorkloadPrecisionReport
check_against_bar(report, *, registered_bar) -> CheckVerdict   # strictly above; None precision → honest advisory
authorization_state(decision_rows, *, max_age: timedelta, now) -> FreshnessVerdict
load_workload_policy(path) -> WorkloadPolicy(max_age_days, binarization_threshold)  # LI-GATE-008, zero defaults
workload_checked_event(*, certificate_hash, generation, report, verdict, policy, now=None) -> StoreEvent
WORKLOAD_CHECK_IFACE_VERSION = "workload-check-v1"
```

## Shadow sampling — `gate/shadow.py` (SM-C1, FR-22 c3)

```python
select_for_shadow(patch_sha256, certificate_hash, *, shadow_rate, salt="") -> bool
  # u = int(sha256(f"{salt}|{cert}|{patch}"),16)/2**256 < rate — deterministic, reproducible, order-independent
make_twin(patch_sha256, certificate_hash, realized_outcome) -> ShadowTwin  # outcomes restricted to LabelOutcome values
compute_sm_c1(twins, *, n_block_decisions) -> SMReport   # false_block_rate = valid_execution share; None when no data
compare_against_budget(report, *, max_false_block_rate) -> BudgetVerdict   # <= budget (owner-ratified), None ≠ compliance
load_shadow_policy(path) -> ShadowPolicy(shadow_rate, salt)   # LI-GATE-010, fail-closed
```

## Deployer CLI surfaces — `packages/gate-adapters/`

- `li-gate-hook-claude` (console script) — Claude Code PreToolUse hook: stdin JSON ≤8 MiB (LI-GADPT-003) → Edit/Write/MultiEdit diffs reconstructed; Bash/NotebookEdit abstain (recorded); exit-0 law on every path (never breaks the agent); wire out = systemMessage + additionalContext, no blocking keys.
- `python -m gate_adapters.mcp_gateway` — JSON-RPC 2.0 `tools/call`; mutating-tools allowlist; abstain → `{"status":"pass-through"}`.
- `python -m gate_adapters.telemetry_etl <log> [--db]` — DuckDB reader over decisions.jsonl: staging+transaction+atomic swap, poison cells counted never crashed, LI-GADPT-004 on bad logs.
- `python -m gate_adapters.workload_check --decisions --store-root --cert-snapshot --cert-pin --generation --policy [--report] [--now]` — the documented FR-21 check (see `governance/gate/workload-check-protocol.md`); appends `workload_checked`.
- `python -m gate_adapters.shadow_report --samples --n-block-decisions --budget --policy --decisions --report [--now]` — SM-C1 report; appends `sm_c1_reported`; report via `open().write()` (AD-4 compatible).

## GHOST MCP — `scripts/mcp/ghost_server.py` / `ghost_http_server.py` (RESEARCH; not the FR-21 gate)

MCP protocol 2025-06-18 · server `ghost` v0.3.0 · HTTP on port 8093 (GHOST_HOST/GHOST_PORT env) · systemd `ghost-mcp.service` on the GPU node.

| Tool | Contract |
|---|---|
| `preflight_patch(repo_path, diff_text)` | deterministic free checks (git apply --check, py_compile, rewrite detection); zero LLM tokens |
| `risk_scan(state_text, diff_text, exclude_task?, reporter?)` | goal-free failure-attractor score over pool v8 (n=207); verdict ONLY in the calibrated regime (LOAO acc 0.952 [0.773,0.992], 10% coverage, tau pinned in `governance/act2/arm-artifacts/risk-scan-v8-calibration.json`) else `abstain`; returns call_id |
| `report_outcome(call_id, passed, reporter?, grounded_by?)` | GROUNDED outcomes only — an issue without a measurement method is rejected from reinforcement; feeds the nightly flywheel (`scripts/act2/mcp_flywheel.py`) |
| `near_mis_patches(state_text, diff_text, goal_text, k)` | k nearest pool neighbors with real outcomes, deduped per task |
| `assess_patch(state_text, diff_text, goal_text)` | GOLD axis, harness/evaluation mode only (requires goal text; unavailable in prod) |

Service honesty: global goal-free AUC 0.615–0.675 (rank, not verdict); the
reliable regime is the 10% where it answers; *abstention is the product*. The
served calibration files are the pinned ground truth; without them the server
refuses to predict.

## Ceremony CLIs — `scripts/prereg/`

- `ceremony.sh <chain_hash>` — live OTS anchor (exit 42 on AnchorUnavailableError); STORE_ROOT env required.
- `release_ceremony.py` — measurement-only publication: build_release_artifacts(packet, release_id slug-checked) → anchor_chain (degrade-with-disclosure: `ots-live | ots-simulated (<exc>)`) → WORM bucket (node) → ledger row → distribute_external (Zenodo/HF; tokens via LI_ZENODO_TOKEN/LI_HF_TOKEN; absent → "SKIP disclosed", never silent crash).
- `certificate_rehearsal.py` / `certificate_ceremony.py` — 7.1/7.5 machinery on temp store roots (fresh dir required); offline-simulated anchors with disclosure; ceremony report JSON cites template hashes + budget seal.

## Ranking — `tools_ranking`

N≥2 candidates ordered by predicted consequence; ties broken explicitly on
(key: score, sha, id) with property tests on the colliding SET (epic 8 lesson:
assert on the set that collides, not mixed contents).
