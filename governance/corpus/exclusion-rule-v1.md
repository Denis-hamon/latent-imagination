# Exclusion rule v1 — rationale + hash of record (story 4.2)

**Strategy, honestly stated.** The rule applies two legs against Noisy-Tier items:
**repo-level** (any repo present in the eval constituents is excluded even across
commits — a memorized repo voids arbitration, R11) and **pr-level** (a declared
`(repo, pr_number)` key is excluded wherever it appears). There is NO instance
leg by construction: noisy items carry no task instance ids — the Noisy Tier is
task-less — so instance-level matching has nothing to bite on. Coverage today is
complete regardless: every constituent instance's repo is folded into the repo
set (`constituents.repo_set`), and `prs: []` makes the pr leg vacuous until the
first PR-keyed constituent is registered.

**Binding (CR 4.2).** `load_rule` resolves `constituents_file` against the repo
root, verifies `constituents_sha256`, and returns the bound set — the filter
never consumes an uncited file. The emit-time AC-2 check re-reads the cited file
fresh (`assert_no_overlap_cited`) so an in-memory filter bug cannot launder a
collision.

## Hash of record

`sha256(exclusion-rule-v1.toml) = 32edbd71cdf7a377920129f033199786e9d1f77256400484ccda52f7b28581e0`

Amendments: bump `rule.version`, rebuild `eval-constituents-vN.json`
(`corpus.constituents.build_constituents`, sources recorded relative so rebuilds
are byte-reproducible), update the cited hash, record the new rule hash here.
Corpus manifests carry `inputs.exclusion_rule_hash` (AD-13), so any artifact can
be traced to the exact governing text.
