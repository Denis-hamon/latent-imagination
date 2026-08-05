# Anchor fallback: RFC-3161 (pyhanko) as OTS alternative

If OpenTimestamps proves unreachable or operationally fragile at ceremony time,
the fallback is an RFC-3161 TSA anchor via `pyhanko` (maintained; supports TSA
client flows). Evaluated 2026-08-05: `rfc3161ng` is stale (last release 2020-10);
`pyhanko` is the live alternative.

The fallback preserves the ceremony contract: hash → anchored proof → ledger row
(type stays `"anchor"`, `ots_proof_ref` becomes `tsa_proof_ref`).
Decision point: BEFORE the first real certificate (Story 7.1), not ad-hoc.
