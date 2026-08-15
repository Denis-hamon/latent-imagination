# Data Models

Domain types live in `packages/core-schema/src/core_schema/` (pydantic
StrictModel, `extra="forbid"`). Persistence is governed by the
store-layout-v1 contract (`packages/store/store-layout-v1/README.md` — that
README is the authoritative text).

## Identity model (AD-12)

All measurement identity is content-derived sha256 (`core_schema/identity.py`):

- `task_fingerprint(repo_full_name, commit_sha, f2p_tests)` — sorted+deduped tests bound into the id (LI-SCHEMA-006 on mismatch).
- `attempt_id(task_id, patch_diff, env_fingerprint, attempt_start)` — canonical JSON of
  `{task_id, patch_sha256: sha256(normalize_diff(diff)), env_fingerprint_sha256, attempt_start_utc}`.
- `normalize_diff` = CRLF→LF + rstrip + trailing `\n`. **Trap**: gate
  annotations hash the RAW diff (`CandidateCtx.patch_sha256`); store snapshots
  hash the normalized diff — joins require exact equality (see
  `docs/../governance/gate/workload-check-protocol.md`).
- uuid7 only for operational correlation (`RunRecord`), never fed to metrics.

## Core domain types

| Type | Key fields | Notes |
|---|---|---|
| `Task` | task_id, repo_full_name, commit_sha, f2p_tests | id validator binds content |
| `PatchProvenance` | model_family, model_version, scaffold_name/version | the only structured "generation" identity in the domain |
| `CandidatePatch` | diff_hash, diff_text_ref, provenance | |
| `EnvironmentFingerprint` | os_family, python_version, container_image_digest, deps_lock_sha256, runner_version | |
| `ExecutionAttempt` | attempt_id, task_id, patch_hash, env_fingerprint, attempt_window, raw_test_output_ref | |
| `Label` | attempt_id, outcome: LabelOutcome, schema_version, ruleset_version, evidence_ref | judge-free (FR-3): derivable from raw trace + ruleset |
| `LabelOutcome` | `valid_execution` · `false_start_tests_ran_no_flip` · `false_start_infrastructure_failure` | infra failure counts as no-flip in F2P metrics |
| `QuarantineRecord` | attempt_id, reason_code (ambiguous_output / missing_f2p / environment_undetermined / duplicate_identity), rule_ids, trace_ref | outside numerator AND denominator |
| `RunRecord` | run_id (uuid7), started_at, purpose | only model allowed clock+uuid (AD-7 occurrence) |
| `StoreEvent` | schema_version=1, kind (past-tense snake, ≥1 underscore), occurred_at (tz-aware), payload dict | Trace Schema envelope; envelope errors LI-SCHEMA-001/002/006 |

Error convention: `SchemaError(code, message, ctx)` serializing
`{code, message, ctx}` per package (`docs/conventions.md`).

## Store layout (store-layout-v1)

```
<store_root>/
  META.json                                  {layout_version, store_version}
  canonical/<id>/<ver>/*.parquet|json        normalized traces, corpus sets
  labels/, quarantine/                       label-sets (reproducible class)
  figures/, bundles/                         harness outputs, replay bundles
  prereg/                                    preregistration manifests + threshold certificates
  releases/                                  release manifests
  chains/<chain16>.json                      AD-5 chains (+ parent_chain amendments)
  proofs/<chain16>.ots                       OpenTimestamps proofs
  prereg-ledger.jsonl                          occurrence ledger (append-only)
```

- `store_version` = sha256(canonical-JSON list of sorted sha256s of `canonical/` data files); empty store = sha256("[]").
- Manifest schema: `{layout_version, artifact_id, artifact_type, artifact_version, artifact_class, producer, inputs, files[{path,sha256,bytes}]}` (+`created_at` occurrence-only).
- **Reproducible classes** (no `created_at`, mandatory `inputs`): canonical-snapshot, labels, quarantine, figure, bundle, arm-artifact, prereg-commit, **threshold-certificate**, release-manifest, corpus-item-set, corpus-release, ranking-report.
- **Writer ownership (AD-4)** — the single source of truth is `store/emit.py:WRITERS`; guards derive from it:

| stage | artifact types |
|---|---|
| traces-ingest | canonical-snapshot |
| labeling | labels, quarantine |
| harness | figure, bundle |
| prereg | prereg-commit, threshold-certificate |
| publication | release-manifest |
| corpus | corpus-item-set, corpus-release |
| tools-ranking | ranking-report |
| probe | arm-artifact |

- Append-only: same id+version with different content → LI-STORE-004; same bytes but different inputs → LI-STORE-008 (bump version).

## Ledger row shapes (`data/release-store/prereg-ledger.jsonl`)

```jsonc
{"type":"anchor", "chain_hash":"<64hex>", "anchored_at":"…Z", "anchor_mode":"ots-live|ots-simulated (<exc>)",
 "ots_proof_ref":"data/release-store/proofs/<16hex>.ots", "components":{…}, "parent_chain":"<64hex>?", "purpose":"…"}
{"type":"run", "run_id":"…", "started_at":"…Z", "ruleset_hash":"<64hex>", "store_version":"<64hex>"}
{"type":"certificate", "certificate_hash":"<64hex>", "direction":"issued|superseding", "verdict_hash":"<64hex>",
 "generations":["…"], "certified_precision":0.93, "registered_bar":0.8889, "issued_at":"…Z", "anchored_at":"…Z",
 "anchor_mode":"…", "ots_proof_ref":"…", "purpose":"…", "supersedes":"<64hex>?", "supersession_reason":"…?"}
{"type":"anchor-failed", …}   // failure state — rows are NEVER deleted (prereg-ceremony.md)
```

## Threshold certificate (prereg, story 7.1)

Content-only body (occurrence metadata stays in ledger rows); hash = sha256 of
canonical JSON excluding `certificate_hash`:

```jsonc
{"kind":"threshold-certificate-v1", "direction":"issued|superseding",
 "verdict_citation":{"artifact":"…","sha256":"<64hex>"},
 "package_citation":{…}, "decision_citation":{…},          // sealed probe-design package + decision.toml
 "generations":["rehearsal-gen-1"],
 "certified_precision":0.93,                                // FRACTION, strictly > bar for issuance
 "precision_wilson95":[0.88,0.96],
 "bar":{"formula":"cost_regen / (cost_regen + cost_exec)",
        "cost_exec_usd":0.0025, "cost_regen_usd":0.0200, "registered_bar":0.8889},
 "signer":{"identity":"…","key_fingerprint":"…"},
 "supersedes":"<64hex>?", "supersession_reason":"…?"}       // superseding only
```

Validity predicate (`prereg.currently_valid`): exists + strict parse of the
whole manifest (one malformed entry poisons the set) + nobody supersedes it +
(optional) query generation ∈ certified set.

## Gate artifacts (deployer-local)

- **Pinned predictor snapshot**: `META.json {layout_version, store_version}` + `predictor.json`
  (`predictor_version: probe-predictor-v0`, `corpus_version: corpus-vN`, `measured{precision, precision_wilson95, posture…}`,
  `vectorizer` recipe (HashingVectorizer mirror 2^12), `model{intercept, coefficients[4096]}`).
- **Certificate hand-off**: `certificate.json` + `supersession-manifest.json {"certificates": {<hash>: <body>}}`.
- **decisions.jsonl** (StoreEvent lines; kinds allowlisted): `gate_annotated` (candidate{patch_sha256}, flip_probability,
  latency_s, predictor_disclosure, prediction_target_tier/detail), `prediction_refused`,
  `candidates_ranked`, `blocking_refused`, `workload_checked`, `patch_blocked` (cost-accounting receipt + budget seal),
  `sm_c1_reported`.
- **Gate event payload for workload checks**: `{n,tp,fp,fn,tn, precision|null, precision_wilson95, binarization_threshold, registered_bar|null, blocking_enabled, reason, max_age_days, generation}`.

## Governance TOML artifacts

- `governance/probe-design/decision.toml` — `[bar]` (registered 0.8889, amendment-only), `[metric]`, `[strictness]`, branches.
- `governance/gate/workload-check-policy-v1.toml` — `[cadence] max_age_days`, `[measurement] binarization_threshold` (fail-closed loader).
- `governance/gate/false-block-budget-v1.toml` — `[budget] max_false_block_rate`, `[derivation]` costs; cited by sha256 seal in every block trace.
- `governance/gate/shadow-sampling-policy-v1.toml` — `[sampling] shadow_rate, salt`.
- `governance/corpus/*.toml` — harvest caps, exclusion rule, hardening policy (pre-registered).
- `governance/ranking/consistency-protocol-v1.toml` — Kendall tau-b protocol.
