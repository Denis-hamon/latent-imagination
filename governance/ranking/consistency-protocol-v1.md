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

`sha256(consistency-protocol-v1.toml) = b73b95dfd6a4db5779e9150058869c96e2eafd5e0365366e71f7130943e8dd05` — computed at registration;
report artifacts cite it as `inputs.ruleset_version` (AD-13).
