# Public field measurement — ERBVE over SWE-smith trajectories (2026-08-06)

The first instrument-published number. Honest provenance: SWE-smith-trajectories
(MIT), 3229 real trajectories labeled by their own task resolution outcomes.
No surrogate judges; labels = `resolved` computed by the tasks' own tests.

**Caveats (binding, in the figure):**
- trajectories-level attempts (not patch-level atomicity) — ERBVE per trajectory-run
- retrospective coverage: SWE-smith's task population is synthesized around real
  repos; not the pre-registered claim-point protocol (that one runs after bases)
- per-family denominators are skewed by the corpus's own attempt mix (claude-3-7
  is over-sampled at 2739 vs gpt-4o's 53) — cross-family comparisons are
  context, not claims.

Files: `../public-measurement-2026-08-06.json` (the figure artifact with the
figure pipeline inputs block), this README.

**Provenance note (history prune):** before the first public push (2026-08-06),
`data/landing/` was purged from git history and is now git-ignored — raw
trajectory `messages` are unsanitized and oversized for git; the corpora stay
on the node / will ship on the dataset surface. Commit hashes changed in the
prune: the node-side release ceremony's `code_commit` (`fd3eae6`) refers to
the pre-prune history. Code content is identical; only landing data was removed.
