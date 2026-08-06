# License inventory v1 (story 4.3, closes addendum §A.6)

**§A.6 flag CLOSED 2026-08-06.** SWE-Gym and R2E-Gym verified **Apache-2.0** via the GitHub
license endpoint of their repos (LICENSE files present). SWE-bench / SWE-smith stay MIT.
HF dataset cards carry no `license` field for SWE-Gym/R2E-Gym — recorded asymmetry: the
code-repo LICENSE is the evidence of record.

**Upstream repos of the local SWE-smith task set (23/23 resolved, zero UNKNOWN):**
GitHub API where it answered (19 repos), license-file content match where the API
returned NOASSERTION (4 repos: flake8/exceptiongroup/typeguard → MIT, boltons → BSD-2-Clause;
evidence column in the JSON names the matched file and branch).

**One copyleft constituent: `Cog-Creators/Red-DiscordBot` = GPL-3.0.** It is NOT in the
harvest-policy allowlist → its tasks route to the audit queue, never into a tier
(harvest-policy-v1 rights rule applied to per-item licenses).

## Hash of record

See the git history of this file pair (`license-inventory-v1.json`); the corpus manifests
cite `inputs.license_inventory_hash` (AD-13).
