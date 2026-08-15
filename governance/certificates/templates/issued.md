# Threshold Certificate — ISSUANCE

> Branch-specific template (commit BEFORE first real issuance — story 7.1;
> rendered mechanically at the 7.5 ceremony; any residual `{placeholder}`
> after rendering is a HARD FAILURE, never shipped text).

## Certificate

- Certificate hash (content identity, AD-12): `{certificate_hash}`
- Direction: `issued`
- Covered model generations: {generations}
- Certified precision (FRACTION, Wilson 95%): {certified_precision} [{wilson_lo}, {wilson_hi}]
- Registered bar (verbatim from decision.toml): {registered_bar}
  (`{bar_formula}`; cost_exec {cost_exec_usd} USD, cost_regen {cost_regen_usd} USD)

## Citations (content hashes, never names)

- Probe verdict artifact: `{verdict_artifact}` @ sha256:{verdict_sha256}
- Sealed probe-design package: `governance/probe-design/package-manifest.json` @ sha256:{package_sha256}
- Bar registration: `governance/probe-design/decision.toml` @ sha256:{decision_sha256}
- Code commit at issuance: {code_commit}

## Signer (per governance/KEYS.md — CI signs nothing)

- Identity: {signer_identity}
- Key fingerprint: {key_fingerprint}

## Anchor

- Mode: {anchor_mode}
- Proof: {proof_ref}
- Anchored at: {anchored_at}

## What this certificate authorizes

Blocking Mode MAY engage ONLY where Story 7.2's per-deployment check measures
the deployer's workload precision strictly above {registered_bar}; at or below
the bar the gate stays advisory and prints the reason (FR-21). Confidence
scores are never an input. Generations outside the certified set keep blocking
off until re-probe.

## Revocation

A re-measurement dropping certified precision to or below the bar issues a NEW
superseding certificate (template: superseding.md) naming this hash and the
reason; this chain is never rewritten (AD-3, erratum protocol).
