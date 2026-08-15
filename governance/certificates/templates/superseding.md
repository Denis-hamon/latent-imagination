# Threshold Certificate — SUPERSEDING (negative-direction release)

> Branch-specific template (commit BEFORE first real issuance — story 7.1;
> rendered mechanically at the 7.5 ceremony or any later revocation; residual
> `{placeholder}` after rendering is a HARD FAILURE).
> Negative-direction artifact: SAME signature discipline as issuance (§7).

## Supersession

- New certificate hash: {certificate_hash}
- Direction: `superseding`
- REVOKED certificate (by content hash): {supersedes}
- Reason: {supersession_reason}

## Re-measurement record

- Certified precision (FRACTION, Wilson 95%): {certified_precision} [{wilson_lo}, {wilson_hi}]
- Registered bar (unchanged — the bar moves BY AMENDMENT, not by edit): {registered_bar}
- Outcome: {above_or_below_bar} (above → re-issuance; at/below → downgrade, Blocking
  Mode announces the downgrade and returns to advisory)

## Citations (content hashes, never names)

- Probe verdict artifact: {verdict_artifact} @ sha256:{verdict_sha256}
- Sealed probe-design package: sha256:{package_sha256}
- Bar registration (decision.toml): sha256:{decision_sha256}
- Code commit: {code_commit}

## Signer (per governance/KEYS.md)

- Identity: {signer_identity}
- Key fingerprint: {key_fingerprint}

## Anchor

- Mode: {anchor_mode}
- Proof: {proof_ref}
- Anchored at: {anchored_at}

## Effect

The revoked certificate {supersedes} ceases to authorize blocking from this
record forward; the ledger carries both rows (append-only, AD-3) and any third
party can re-derive validity offline via `prereg.currently_valid`.
