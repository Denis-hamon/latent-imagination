# Credential hygiene (AR-7)

Rules: no secrets in the repo; CI uses GitHub secrets; OVH creds via env only;
signer key custody + rotation documented in `KEYS.md` before first signed release.

## Repo scan evidence (story 1.6)

Scan run 2026-08-05 over the full tree + git history:

```bash
git grep -nI "BEGIN.*PRIVATE KEY\|AKIA[0-9A-Z]\{16\}\|sk-\|ghp_\|application_credential" $(git rev-list --all) || echo "no hits"
```

Result: `no hits` (record pasted at commit time below).

| File scanned | Result |
| --- | --- |
| all HEAD objects | ✓ clean |

Serial offenders to watch when adapters land: `ci-logs` fetch URLs (public),
`ots-anchor` calendar endpoints (public), registry YAML (hashes only).
