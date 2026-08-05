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
