# Anchor fallback: RFC-3161 (pyhanko) as OTS alternative

If OpenTimestamps proves unreachable or operationally fragile at ceremony time,
the fallback is an RFC-3161 TSA anchor via `pyhanko` (maintained; supports TSA
client flows). Evaluated 2026-08-05: `rfc3161ng` is stale (last release 2020-10);
`pyhanko` is the live alternative.

The fallback preserves the ceremony contract: hash → anchored proof → ledger row
(type stays `"anchor"`, `ots_proof_ref` becomes `tsa_proof_ref`).
Decision point: BEFORE the first real certificate (Story 7.1), not ad-hoc.

## Decision — recorded at Story 7.1 (2026-08-15)

OTS (opentimestamps-client 0.7.2, `ots` console script) REMAINS the primary
anchor for threshold certificates. Basis: a live anchor was already obtained
for chain `3ff03b8a…` at the v0.1.0 release (committed proof byte-parsed by
`prereg.verify_proof_bytes`), and Story 7.1's rehearsal
(`scripts/prereg/certificate_rehearsal.py`) exercises the identical anchor
mechanics on the disclosed offline-simulated lane. pyhanko/RFC-3161 remains
the documented fallback lane if OTS calendars prove unreachable or fragile at
ceremony time; the contract preservation above (row type unchanged, proof-ref
field swaps to `tsa_proof_ref`) is the switching rule.

The open action item "Write TSA fallback live test during the first real
ceremony" (sprint-status.yaml) stays OPEN and binds to Story 7.5's live
ceremony — the first real certificate issuance — not to this machinery story.
