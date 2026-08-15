# Pre-registration Ceremony

Freeze → hash → anchor → record. Anything that governs a decisive run
(ruleset, margin, threshold, tolerance…) passes through this BEFORE the run.

## Steps

1. **Freeze.** The artifact(s) are final: no edits until after the run.
2. **Hash.** Compute the chain via `li-prereg.assemble_chain(release, bundle, snapshot, ruleset, code_commit)`; the chain_hash is canonical (sort_keys, tight JSON).
3. **Anchor.** Run `scripts/prereg/ceremony.sh <chain_hash>` which calls the OTS calendars via `li-ots-anchor` (network only here; adapters exemption). On any failure see "Failure states" below.
4. **Record.** Append the anchor row to `<store_root>/prereg-ledger.jsonl` via `li-prereg.ledger.anchor_entry(...)`. Verify with `verify_offline`.

## Failure states

- **Calendar unreachable** (`AnchorUnavailableError`): retry with backoff (60s ×5). If still unreachable, do NOT delete ledger rows — write a `{"type":"anchor-failed", ...}` row noting the attempt, and fall back per `governance/anchor-fallback.md`.
- **Partial upload** (some calendars OK, others not): the proof is valid once ANY calendar responds; record which ones under `ots_proof_ref`.
- **Duplicate anchor**: idempotent — the same chain_hash re-anchored is a no-op; the ledger holds one row per (chain_hash, anchored_at).

## Verification by a third party

Anyone with the ledger + the artifact can run `li-prereg.verify_offline(manifest, record)` — no network, no credentials.

## Threshold certificate ceremony (Story 7.1, FR-21)

Certificates are prereg artifacts (AD-9): issuance and supersession follow this
runbook; the FIRST LIVE ceremony is Story 7.5 and requires a probe verdict that
crossed the registered bar — machinery rehearsal (`scripts/prereg/
certificate_rehearsal.py`) runs offline only.

1. **Assemble.** `li-prereg.assemble_certificate(...)` — fail-closed: refusal
   `LI-PRERE-002` if certified precision is at/below the registered bar
   (no configuration permits issuing there). Citations bind the verdict
   artifact, the sealed probe-design package, and decision.toml by sha256.
2. **Byte-verify.** `li-prereg.verify_certificate_bytes(cert, verdict_bytes,
   package_manifest_bytes, decision_bytes)` — equality proofs on bytes.
3. **Store.** `store.write_artifact("prereg", "threshold-certificate", ...)`
   — reproducible class, zone `prereg/`, inputs block cites the three content
   hashes + code commit (AD-13).
4. **Anchor.** Live: `scripts/prereg/ceremony.sh <certificate_hash>` (OTS);
   fallback lane per `governance/anchor-fallback.md` (decision recorded
   2026-08-15: OTS primary). Rehearsal: offline-simulated with disclosure.
5. **Record.** Append `li-prereg.ledger.certificate_entry(...)` to the ledger.
   Supersession appends a NEW row naming the revoked certificate + reason —
   do NOT delete or edit ledger rows (AD-3, erratum-protocol.md). Negative
   direction carries the same signature discipline (§7).
6. **Verify.** Anyone with ledger + artifacts re-derives validity offline:
   `verify_certificate_bytes` + `currently_valid` — no network, no credentials.

## First-issuance ceremony (Story 7.5, FR-21)

The first blocking authorization is a PUBLIC ceremony — phase 4 starts on a
witnessed, reproducible footing. The ceremony composes the certificate into a
release packet via the 2.6 release machinery (`release_ceremony.
build_release_artifacts` + `anchor_chain`), the ledger carries the release
row, and the ceremony page (rendered from `governance/certificates/templates/
issued.md`) links the 7.1 revocation-drill artifacts.

The LIVE ceremony (real OTS anchor, WORM bucket, Zenodo DOI, HF mirror, real
verdict hash citing a crossing-bar probe verdict) is GATED by doctrine — no
arm crossed 0.8889 (branch iii). The ceremony machinery is proven on fixtures
(`scripts/prereg/certificate_ceremony.py`) with the same offline-simulated-
with-disclosure pattern as 7.1's rehearsal. Field validation
(`tests/e2e/test_certificate_ceremony_field_validation.py`) proves blocking is
active ONLY under certificate + local-check conditions — the integration test
tying 7.1+7.2+7.3+7.4 together.
