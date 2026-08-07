# Ordering-consistency protocol v1 — rationale (story 8.3)

Kendall tau-b per task over candidates, macro mean over defined tasks — chosen because
it handles tie groups properly (the ranking tool has explicit tie groups, FR-23), needs
no distributional assumption, and reads directly as "fraction of pair orderings the tool
gets right".

Degenerate rule (registered before any evaluation): an all-tied predicted or realized
side makes tau-b mathematically undefined (zero denominator) — we record it as
`undefined`, count it, never coerce to ±1. A split whose every task degenerate
publishes with the caveat in the header (same ladder discipline as the Clean Tier).

Held-out split: seeded (20260806), deterministic, disjoint from any calibration split
by construction — the exclusion set names what it excludes and the split manifest is
a committed artifact.

Real evaluation runs happen when a trained predictor exists (post-cycle); the evaluator
+ protocol + fixtures ship now, and the report's fertility is gated by data, not by code.

## Hash of record

`sha256(consistency-protocol-v1.toml) = ce25f0db6b4bb580150113c17cbf59e08328b54f5e617e4ded25342f8c6d38c8` — computed at registration;
report artifacts cite it as `inputs.ruleset_version` (AD-13).
