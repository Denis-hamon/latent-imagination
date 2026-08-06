# corpus — two-tier Patch→Consequence corpus (phase 2+)

Core package (AD-6: zero network at run time). The harvest's network lives in
`packages/adapters/ci-logs`; this package reads the landing zone only.

## Noisy-tier canonical identity (THE mapping rule)

- **task** = `(repo_full_name, head_commit_sha, f2p_tests=())` — noisy items
  carry NO fail-to-pass list; the test slot of the task fingerprint is the
  empty tuple. The Noisy Tier is pretraining substrate, NOT measurement data
  (measurement-grade F2P flips are the Clean Tier's job, stories 4.2/4.3).
- **attempt** = `core_schema.identity.attempt_id(task_id, sanitized_patch,
  env, run_created_at)` — identity is computed ONLY in `core-schema` (AD-12).
  Re-running a harvest window re-derives identical item ids (resumable,
  idempotent; FR-2); cross-source duplicates collapse to one primary entry.
- **environment**: public-CI environments are not observed → the single
  documented constant `noisy.UNOBSERVED_ENV` is used.
- **sanitization**: the frozen patterns of `governance/sanitize-policy.toml`
  run on patch CONTENT before hashing/storage; per-item counts are lineage
  (FR-2's published-counts duty).
- **rights**: license not in the harvest-policy allowlist → audit queue, never
  a tier (`governance/corpus/harvest-policy-v1.toml`, pre-registered numbers).

## Modules

| module | role |
| --- | --- |
| `policy.py` | loads the pre-registered harvest policy (fail-loud, LI-CORPUS-001/2) |
| `noisy.py` | landing deposits → deduped/sanitized/rights-filtered items |
| `atif_drift.py` | drift watch: schema_version actually seen vs the pinned one (AC 2) |
| `emit.py` | `corpus-item-set` artifacts into the store (canonical zone, AD-4/AD-13) |

Error codes allocated here: `LI-CORPUS-001..004`.
