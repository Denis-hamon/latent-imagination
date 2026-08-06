# OQ-10 resolution — deployment-time prediction-target policy (RESOLVED 2026-08-06, story 5.1)

**Question** (PRD §12): on a non-annotated user repo, which test set does the gate predict
against?

**Resolution — three-tier fallback, abstention-first:**
1. **Diff-touched tests**: if the Candidate Patch touches test files, the prediction target is
   that touched set (the patch introduces/updates its own F2P candidates).
2. **User-designated selection**: else, the deployer designates the test selection in the gate
   config (`gate` settings, `LI_`-prefixed env) — recorded in the decision log per annotation.
3. **ABSTAIN**: if neither exists, the gate emits NO flip prediction. A gate that invents a
   denominator would violate the judge-free doctrine (FR-9) and the quarantine discipline
   (FR-3) — silence is the honest output, disclosed as abstention coverage in the pilot report.

Abstention is verifiable: annotations carry `predictor_disclosure`, and the log records which
tier served (or `abstained`). Any future adoption claim must cite this file.
