# Per-deployment workload check — protocol (Story 7.2, FR-21 c1)

FR-21 c1: blocking authorization "cites the probe verdict artifact by hash
(evidence the shipped method exceeds the bar) **AND** requires a
per-deployment precision check on the deployer's workload to remain strictly
above the bar (protocol in gate docs)." This document is that protocol.

## What the check answers

"Does THIS deployment's OWN labeled history show the predictor flips correctly
often enough to justify blocking here?" A global verdict (even a crossing one)
never shields a local misfit.

## Invocation

```sh
python -m gate_adapters.workload_check \
    --decisions ~/.latent-imagination/decisions.jsonl \
    --store-root /path/to/deployer-local-store \
    --cert-snapshot /path/to/pinned-cert-handoff \
    --cert-pin <64-hex certificate content hash> \
    --generation <this deployment's model generation> \
    --report workload-check-report.json
```

The check APPENDS a `workload_checked` event to the decision log. It writes to
nothing else (the gate never writes canonical stores, AD-4).

## The three legs (fail-closed composition)

1. **Certificate authorization** (`gate.blocking.authorize_blocking`, Story
   7.1): the pinned certificate is byte-verified, currently valid (not
   superseded), names this deployment's generation, and its certified
   precision is strictly above the bar. Any failure → advisory, reason names
   the leg.
2. **Local measurement**: precision measured from the deployer's own
   joined history is STRICTLY above the certificate's registered bar. At or
   below → advisory; the reason is printed and recorded. `None` precision
   (no positive predictions) is honest undefined, never 0.0, and authorizes
   nothing.
3. **Freshness**: checks re-run on a schedule. The policy
   (`governance/gate/workload-check-policy-v1.toml`, `[cadence] max_age_days`,
   values move BY AMENDMENT ONLY) defines staleness: an absent or expired
   `workload_checked` event permits no blocking between runs. The enforcement
   seam (Story 7.3) must consult `gate.workload_check.authorization_state`
   before any block.

Blocking is enabled only when legs 1 AND 2 pass; leg 3 governs how long that
authorization stays trustworthy between re-runs.

## Measurement honesty (OQ-10; FR-3; FR-9)

- **Denominator is joined, never invented.** Rows enter measurement only when
  a decision-log annotation joins through BOTH identity hops to a realized
  label: `decisions.jsonl (gate_annotated)` —`patch_sha256`→ canonical
  snapshot row (`attempt_id`) —`attempt_id`→ labels row (`outcome`).
- **The identity trap.** Decision logs record `sha256` of the RAW
  reconstructed diff (`CandidateCtx`); store snapshots record
  `sha256(identity.normalize_diff(diff))`. These coincide only when the diff
  is already in normal form (LF endings, single trailing newline). Annotations
  that cannot join exactly are counted `unmatched` and EXCLUDED.
- **Abstentions excluded.** `prediction_refused` events are counted and
  disclosed, never evidence.
- **Ambiguity excluded.** A patch that joins to conflicting outcomes is
  counted `ambiguous` and dropped — the check never guesses.
- **Poison tolerated.** Torn log lines / unparseable store files are counted
  and skipped; a corrupted deployer input cannot crash the check (5.6 law).

## Ground truth mapping (judge-free)

Outcomes are the deterministic labels of `labeling/rules_v1.py` (FR-3, FR-9 —
no human or LLM classification):

| Label outcome | Flip observed? | Counts as |
|---|---|---|
| `valid_execution` | yes | true (1) |
| `false_start_tests_ran_no_flip` | no | false (0) |
| `false_start_infrastructure_failure` | no | false (0) — conservative F2P reading |

Quarantine records are never Labels and never enter the check.

## Binarization & units

A prediction is a flip prediction iff `flip_probability > binarization_threshold`
(strict). Default threshold 0.5 mirrors the probe's sklearn LogReg `predict()`
boundary (`probe.arms.baseline`) — the value is pre-registered in the policy
TOML and restated in every report. Precision = tp/(tp+fp) in FRACTIONS;
Wilson 95% interval (the `[metric] ci_method` pre-registered in
`decision.toml`). `_pp` suffixes appear only in human display prose.

## Confidence scores are never an input (FR-21)

`WorkloadRow` is a closed schema: exactly `patch_sha256`, `flip_probability`,
`prediction_target_tier`, `outcome`. Any extra field — `confidence`,
`confidence_tier`, scores of any kind — fails validation. The measurement
functions accept nothing else. This is property-tested in
`packages/gate/tests/test_workload_check.py` and behaviorally in the CLI suite.

## Strictness regimes (do not unify)

- Probe VERDICT crossing: `precision >= registered_bar` (decision.toml
  `[strictness]` — inclusive).
- BLOCKING authorization (this check + the certificate): `precision >
  registered_bar` (FR-21 — strictly above). The two differ by design; a value
  exactly on the bar crosses the verdict boundary but never authorizes
  blocking.

## Generation naming

The deployment NAMES its generation via `--generation` (no default, no
inference). A generation outside the certificate's named set keeps blocking
off until re-probe (FR-21 c2 freshness) — the refusal cites the certified set.

## Blocking decision path (Story 7.3, FR-22)

When BOTH legs above hold, the decision route lives in
`gate.blocking.evaluate_blocking` — the single allowlisted blocking surface:

```
budget pre-registered?  --no-->  ADVISE (FR-22: budget before blocking)
local check enabled (strict bool)?  --no-->  ADVISE
recorded local precision strictly above bar?  --no-->  ADVISE (flag alone never trusted)
check fresh (now - checked_at <= max_age_days)?  --no-->  ADVISE (expired lapses blocking)
denominator tier valid (OQ-10)?  --no-->  ADVISE (no block without a denominator)
flip predicted (p > binarization_threshold, strict)?  --no-->  ADVISE
otherwise -> BLOCK, and a `patch_blocked` trace is emitted.
```

- **Trace contract (FR-22 c2).** Every block emits a `patch_blocked`
  StoreEvent (Trace Schema envelope) to the deployer-local decision log —
  NEVER a canonical store (AD-4 fence; the decisions log is the deployer-local
  surface per story 5.1). Payload: candidate {repo, patch_sha256}, prediction
  {flip_probability, tier, binarization_threshold}, certificate_hash,
  local_precision_estimate, registered_bar, cost_accounting {cost_exec_usd,
  cost_regen_usd, expected_regen_cost_usd, budget_seal_sha256}, reason. The
  cost accounting QUOTES the budget's derivation inputs — no live prices, no
  oracle, no network.
- **Budget seal.** The false-block budget is
  `governance/gate/false-block-budget-v1.toml`, pre-registered per FR-22 c1.
  Seal (sha256 of the file's exact bytes), frozen 2026-08-15:
  `51c2ff3f1ae6d58d81dd6dd60cf806858a63b09fa53f78d879a35e323c91be72`.
  Every block trace cites this seal; an edit without amendment moves the seal
  and breaks the audit chain. Values are [ASSUMPTION]-tagged until the Story
  7.5 ceremony ratifies them.
- **Audit chain.** trace.certificate_hash → certificate body (hash
  re-derivation) → verdict_citation.sha256 → probe verdict bytes. Every hop
  byte-provable offline (`compute_certificate_hash`,
  `verify_certificate_bytes`). Proven property: NO configuration permits a
  block when either precision leg is at/below the bar (seeded sweep,
  `test_blocking_decision.py`).
- **Adapter enforcement stays OFF** in phase 4 machinery: hooks/gateway remain
  advisory (FR-19 default); a live block requires a ceremony-issued
  certificate (Story 7.5) plus this decision path plus the deployment's own
  authorization. The seam is proven on fixtures until then.

## Re-running

The check is one command against the deployer's own files; re-running
regenerates the record (bit-rot policy parity with 5.6 telemetry). Scheduling
belongs to the deployer; the protocol guarantees only that an authorization
older than `max_age_days` is worthless.
