# Stylistic controls (FR-14)

Execution-free verifiers lean on stylistic features (R2E-Gym). Our arbitration
must prove a style-correlated lift is disclosed, not hidden.

Protocol:
1. Strate the eval set by patch-style buckets (diff length, comment density,
   presence of docstring changes).
2. Report per-stratum precision for BOTH arms alongside headline precision.
3. A lift that lives in exactly one style stratum is flagged in the verdict doc
   as "style-correlated", never silently folded into the claim.
4. If a stratum has < 30 items, the control is marked "underpowered", not ignored.
