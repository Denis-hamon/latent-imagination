# Shadow-mode sampling & SM-C1 (Story 7.4, FR-22 c3)

FR-22 c3: while Blocking Mode is on, shadow-mode sampling is the **mandated**
measurement path for the false-block rate (SM-C1). This document publishes the
mechanism, the pre-registered values, and the computation.

## Definitions

- **Shadowed block**: a blocking decision that is ALSO executed as an advisory
  twin — the patch runs anyway under observation and its realized outcome is
  recorded against the block.
- **False block**: a shadowed block whose realized outcome is
  `valid_execution` — the blocked patch actually flipped and passed. The gate
  blocked a patch that would have worked: this is what the budget caps.
- **SM-C1**: `false_block_rate = n_false_block / n_shadowed`, with a Wilson 95%
  interval (the `[metric] ci_method` pre-registered in decision.toml), compared
  to `max_false_block_rate` in `false-block-budget-v1.toml`.

## Pre-registration (FR-22 §7 item)

`governance/gate/shadow-sampling-policy-v1.toml`:

- `shadow_rate = 0.10` — 1 in 10 block decisions shadowed. [ASSUMPTION until
  the 7.5 ceremony ratifies]
- `salt = "shadow-v1"` — replay domain separator.

The budget file's `shadow_sampling_ptr` names exactly this policy; the pointer
is closed by this story. Values move BY AMENDMENT ONLY.

## The sampler

`gate.shadow.select_for_shadow(patch_sha256, certificate_hash, *, shadow_rate,
salt)` — deterministic, reproducible, order-independent:

```
u = int(sha256(f"{salt}|{certificate_hash}|{patch_sha256}"), 16) / 2**256
sampled iff u < shadow_rate
```

Binding the certificate hash scopes the sample to a specific authorization: a
supersession (new certificate) intentionally re-rolls who is shadowed —
matching generation-scoped certificates (FR-21 c2). Same identity ⇒ same
decision, forever: re-running never changes who was shadowed (auditable).

## The report

`python -m gate_adapters.shadow_report` over the deployer's own files:

- reads the deployer-local twin log (streamed, BOM-tolerant, poison lines
  counted + skipped, never fatal — 5.6 law);
- computes SM-C1 + sampled share;
- compares against the budget seal (sha256 of the budget file's exact bytes);
- appends one `sm_c1_reported` event to the deployer-local decision log and
  writes a report JSON to the deployer-chosen path — NEVER a canonical store
  (AD-4 fence; the decisions log is the deployer-local surface per 5.1).

Cadence: the deployer re-runs the command; each run lands a report "on
cadence" (the mechanism re-generates the record, bit-rot policy parity).

## Honesty rules

- `false_block_rate = None` when nothing was shadowed — undefined is not
  compliance; `compare_against_budget` refuses None as not-within-budget.
- Realized outcomes are only the three judge-free `LabelOutcome` values
  (FR-3/FR-9); any other string is rejected.
- Phase-4 disclosure: no live block exists yet (branch iii, no certificate).
  The demonstration pilot (`packages/gate-adapters/tests/fixtures/
  shadow-pilot-samples.jsonl`) is SYNTHETIC and labeled as such in every
  report (`pilot_disclosure`). Real twin execution begins only when a live
  block can occur (Story 7.5 ceremony + deployment authorization reviving the
  adapter enforcement seam).

## Revocation linkage

A re-measurement of SM-C1 above the budget is a revocation trigger for the
certificate (FR-21 c3): the superseding certificate's reason cites the
`sm_c1_reported` evidence. The budget rationale (story 7.3) names the
consequence: over-blocking is measurable, and measurably over budget means
downgrade, not silence.
