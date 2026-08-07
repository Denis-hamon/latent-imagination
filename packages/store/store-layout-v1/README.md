# store-layout-v1 — the contract

This document IS the contract. Everything in `packages/store` is a thin helper
against it; readers need only this README + `duckdb`.

## Tree

```text
<store_root>/
  META.json                                   # {layout_version, store_version}
  canonical/                                  # reproducible: normalized traces/snapshots
    <artifact_id>/<artifact_version>/*.parquet|*.json
    manifests/<artifact_id>.<artifact_version>.artifact.json
  labels/<artifact_id>/<artifact_version>/…   # label-sets
  labels/manifests/…
  quarantine/<artifact_id>/<artifact_version>/…
  quarantine/manifests/…
  figures/<figure_id>/<version>/{*.json,*.csv,*.png}
  figures/manifests/…
  bundles/                                    # replay bundles (harness-owned)
  prereg/                                     # preregistration manifests
  releases/                                   # release manifests
```

Raw adapter deposits do NOT live here — they land in `data/landing/`
(occurrence files + `.landing-manifest.json`).

## Manifest schema (every artifact has one)

```json
{
  "layout_version": "store-layout-v1",
  "artifact_id": "string",
  "artifact_type": "one of the known types",
  "artifact_version": "string",
  "artifact_class": "reproducible | occurrence",
  "producer": "owning stage name",
  "inputs": {"store_snapshot": "…", "ruleset_version": "…", "code_commit": "…", "seeds": {}},
  "files": [{"path": "relative/…", "sha256": "…", "bytes": 123}]
}
```

- **Reproducible-class** manifests carry NO `created_at` and no uuid — content only (AD-7).
- **Occurrence-class** manifests carry `created_at` (ISO-8601 UTC). No store zones hold
  occurrence artifacts today (those live in `data/landing/`).
- **inputs** is MANDATORY for reproducible artifacts (AD-13).
- ids/versions match `^[a-z0-9][a-z0-9._-]*$` — no traversal, no uppercase.
- Duplicate basenames within one write are rejected. Same id+version re-emitted with
  IDENTICAL content hashes is a no-op (idempotent ingest); different content fails.

## Rules

1. **Append-only.** An existing artifact path is never rewritten with different
   content; corrections are a new `artifact_version`.
2. **Ownership (AD-4).** Only the owning stage's name may appear as `producer`
   for a type (table below). It is enforced at write time in `store/emit.py`
   AND re-checked at validate time (a manifest whose producer doesn't own the
   type is invalid) — so a renamed caller de.validate fails too.
3. **Content-addressing.** `store_version` = sha256 over the canonical-JSON list of the
   sorted content hashes of `canonical/` data files; empty store = sha256("[]").
   `store-validate` RECOMPUTES it against META.json at every run.
4. **Prereg precedence.** When `prereg-ledger.jsonl` exists at the store root, EVERY
   `labels` AND `quarantine` manifest must link through `inputs.run_id` to a ledger
   run row whose ruleset was anchored before the run started. Missing prereg package
   with a ledger present is a FAIL, not a skip (fail-closed).

## Writer ownership table

| stage | artifact types |
| --- | --- |
| traces-ingest | canonical-snapshot |
| labeling | labels, quarantine |
| harness | figure, bundle |
| prereg | prereg-commit |
| publication | release-manifest |
| corpus | corpus-item-set, corpus-release |
| tools-ranking | ranking-report |

## Reading the store (reproducer path)

No library needed. Artifacts are parquet/json/png under the paths above; figure
inputs are named in each figure's manifest `inputs` block. `packages/store/views.py`
ships DuckDB views marked **convenience, never obligation** (AD-8): they read exactly
the paths documented here — never anything else.

