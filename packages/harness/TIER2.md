# TIER-2 kit — end-to-end re-execution for auditors

Tier 2 re-executes the claim-point tasks themselves (not just the arithmetic).
Heavier, separately scoped, cost-disclosed. Everything below is the kit's
contract; who runs it and how is the caller's ceremony.

## Scope

- Claim-point task list: `governance/act1-design/tasks.toml` (frozen).
- Required floor: Docker-capable host (own harbor runner) OR an equivalent
  environment-pinned runner. Python 3.14 toolchain for analysis steps.

## Cost & time (disclosed, not discovered)

| Item | Estimate | Notes |
| --- | --- | --- |
| API tokens per claim task | `≤ $1-5/task` heuristically; actuals land in `budget.md` per campaign | drives `budget.cap_usd` |
| Wall time | `~5-15 min/task` | stop-at-first-valid bounds this upward-bounded |

## Tolerance (pre-registered answer to OQ-5)

- **Value:** ±2.0 pp on the claim-line macro_rate vs published.
- **Inclusivity:** inclusive — "within tolerance" means `|delta| ≤ 2.0`.
- **What it covers:** environment nondeterminism between the published host and
  the auditor's host. It does NOT cover: a different ruleset version, a different
  store slice, a changed task list — those are differently-versioned measurements,
  not tolerance cases.

## Divergence → env-diff report

A failed tolerance check prints a named env-diff: python/setup versions, registry
snapshot versions, and the first diverging artifact id. Never "didn't match".

## Manifests & artifacts

Every run of the kit produces occurrence-class manifests (the audit trail of the
re-execution event) under `tier2_kit/runs/<run_id>/`. The measured outputs
(parquet/csv) remain reproducible-class content inside those manifests' references.
