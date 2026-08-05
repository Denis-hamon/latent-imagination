# Consistency Conventions

Binding conventions from the architecture spine (AD-1..AD-14 govern invariants; this table governs daily drift). Source of truth: `ARCHITECTURE-SPINE.md` in the planning workspace — any change there wins over this copy, and changes here must be reflected upstream.

| Concern | Convention |
| --- | --- |
| Naming | Packages kebab-case under `packages/`, edges under `packages/adapters/`; modules snake_case; domain terms strictly per PRD Glossary (verbatim, capitalized as defined); emitted event names past-tense snake_case (`attempt_labeled`, `snapshot_published`) |
| Data & formats | Timestamps ISO-8601 UTC `Z`; measurement identity per AD-12 (content-hash); operational ids uuid7; manifests JSON; analysis files parquet; reproducible artifacts content-only per AD-7 (no wall-clock/uuid) |
| Error handling | Typed exceptions, stable codes allocated per package: `LI-<PKG>-nnn` (e.g., `LI-STORE-001`); errors serialize `{code, message, ctx}` |
| Config | pydantic-settings; env prefix `LI_`; config files TOML committed; all seeds in committed configs |
| Logging | Structured jsonl `{ts, level, event, ctx}`; run-logs are occurrence artifacts |
| Registries (FR-1) | YAML files in `data/registries/`, schema-validated by `core-schema` |
| Replay bundles (Tier 1/2) | Owned by harness (AD-4): store slice + ruleset pin + figure pipeline + manifest (inputs block per AD-13); releases reference the bundle hash (AD-5) |
| Secrets & keys | No secrets in repo; CI uses GitHub secrets; OVH credentials via env only; signer key custody + rotation documented in `governance/KEYS.md` before the first signed release |
| Dependencies | Single lockfile committed; new dependency = exact pin + one-line rationale in the planning memlog; no dependency in a core package may add network clients (AD-6; exemption scope: `packages/adapters/*` only) |
| Tests | Per-package `tests/` + top-level `tests/` for e2e, determinism replays, and the CI guard suite (import-lint, writer inventory, dependency-scan, network sandbox) |

## Commit hygiene

- One story = one commit, staging explicit paths. Never `git add -A`.
- A gate must prove the FUNCTION (test the check, not its presence).
