# Harvest policy v1 — rationale (pre-registered, story 4.1)

The Noisy Tier harvest is the project's first sustained outbound collection. R10 requires a
pre-registered cap per phase: these numbers are the Phase-2 opening values, deliberately
conservative; a cadence review at Epic-4 exit can amend them upward (bump `version`, cite the
old policy hash in the corpus manifest `inputs` chain — AD-13).

- **`rest_requests_per_day = 20,000`** — GitHub PAT primary budget is 5,000 requests/hour
  (docs.github.com/rest/rate-limits, verified 2026-08-06). The cap spends ~4 hours of full
  burn per day and leaves headroom for everything else this account does.
- **`max_diff_fetches_per_repo_day = 1,500`** — per-PR `.diff` web fetches dominate the cost.
  A hot repo's daily PR flow is ≪1,500; the cap tails abuse of any single host.
- **Politeness**: 1 s per-host minimum interval (robots.txt fetches included — the spike's
  convention, RFC 9309-ish: 404 → allow, 5xx → block, other 4xx → allow; the stricter-reading
  option remains an owner call, recorded in the deferred-work ledger).
- **403/429**: wait until `x-ratelimit-reset`; secondary limits honor `retry-after`, else
  exponential backoff (60 s × 2ⁿ, n ≤ 5) — then a hard failure, never a hammer.
- **Rights**: permissive-license allowlist only (`license_allowlist`); `UNKNOWN` routes to the
  audit queue, never to a tier. License remediation post-publication follows §5.4/FR-17.
- **Noise handling**: dedup = canonical attempt identity (FR-2) computed by
  `core_schema.identity` — the only place identity exists (AD-12). The flaky policy is the
  frozen FR-4 document (`governance/labeling-decision-tree.md` + `labeling` rules_v1); this
  policy cites it rather than redefining it, so there is exactly one flaky policy.
- **Sanitization**: the frozen patterns of `governance/sanitize-policy.toml` run on patch
  CONTENT at harvest time (patch text is the corpus item — content-level, not just record
  metadata); per-item counts are part of the item's lineage (FR-2 published-counts duty).
- **Drift watch**: expected ATIF version `ATIF-v1.7`, matching the pin in
  `core_schema.trace.ExecutionTrace.schema_version`; the watch reports drift rather than
  hard-failing so an upstream format move surfaces as information, not silence (addendum
  §E.4 note 3: ATIF = alignment, not pin — drift risk is owned by this phase).
