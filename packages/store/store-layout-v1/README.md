# store-layout-v1 — the contract

This document IS the contract. Everything in `packages/store` is a thin helper
against it; readers need only this README + `duckdb`.

## Tree

```text
<store_root>/
  META.json                        # {layout_version, store_version}
  canonical/                       # reproducible artifacts (normalized traces, snapshots)
    snapshots/<store_version>/*.parquet
    manifests/<artifact_id>.<artifact_version>.artifact.json
  labels/<ruleset_version>/…       # label-sets
  quarantine/<ruleset_version>/…   # quarantine records (labeling-owned)
  figures/<figure_id>/<version>/   # published figures (json/csv/png)
  bundles/                         # replay bundles (harness-owned)
  prereg/                          # preregistration manifests
  releases/                        # release manifests
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
- **Occurrence-class** manifests carry `created_at` (ISO-8601 UTC). Today no store zones
  hold occurrence artifacts (they live in `data/landing/`).
- **inputs** is MANDATORY for reproducible artifacts (AD-13).

## Rules

1. **Append-only.** An existing artifact path is never rewritten; corrections are a new
   `artifact_version`. The emit helper refuses overwrites; the validator detects
   same-id+version re-published with different content.
2. **Ownership (AD-4).** Only the owning stage writes a type (see table below);
   enforced in `store/emit.py` AND re-checked by the validator (manifests whose producer
   doesn't own the type are invalid).
3. **Content-addressing.** `store_version` = sha256 over the canonical-JSON list of the
   sorted content hashes of `canonical/` data files; empty store = sha256("[]").
4. **Prereg precedence.** When `prereg-ledger.jsonl` exists at the store root, the
   validator verifies that every label-set's ruleset was anchored BEFORE its run
   (delegated to the `prereg` package).

## Writer ownership table

| stage | artifact types |
| --- | --- |
| traces-ingest | canonical-snapshot |
| labeling | labels, quarantine |
| harness | figure, bundle |
| prereg | prereg-commit |
| publication | release-manifest |

## Reading the store (reproducer path)

No library needed. Artifacts are parquet/json/png under the paths above; figure
inputs are named in each figure's manifest `inputs` block. `packages/store/views.py`
ships DuckDB views marked **convenience, never obligation** (AD-8): they read exactly
the paths documented here — never anything else.
