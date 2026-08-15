# Window GEN-FAMILIES — targeted pool growth by family (pre-registration v1)

Status: APPROVED 2026-08-15 — owner ratified the session envelope (350-call
cap Q1+Q2, quotas Q1 120 / Q2 20 / Q3 ≤30 optional) at session approval.
Values still move BY AMENDMENT ONLY, before any spend.
Seal: sha256 of this file's frozen bytes is to be recorded in the prereg
ledger at the next ceremony window (same discipline as rct-prereg-v1 /
ladder-prereg-v1). Execution requires explicit owner approval of a session
envelope — this document registers the PROTOCOL, not a run.

## Why (measured, not speculated)

Pool v8 (n=207, 73 positives, 2026-08-15) coverage facts:

- 54 task families (repo prefixes); **33 of 54 families have ≤ 3 rows** —
  most families cannot sustain any per-family statistic.
- S14 evaluation decomposition: rows from families unseen before v7 score
  0.750 AUC and produce confident errors that break the tail, while v7-era
  rows climb to 0.870 in the v8 geometry. Coverage, not capacity, is the
  binding constraint on the reliable regime.
- GHOST v0.4.0 abstentions now NAME the out-of-coverage family — the
  abstention diagnostics (e.g. governance-style queries during the Epic 7
  session) point at exactly the families to grow.
- S11 poison lesson: pool mixing is measured BEFORE building. Author model is
  therefore PINNED (below), one author per window, no silent blending.

## Targets & quotas

| Quota | What | Cap |
|---|---|---|
| Q1 new-repo families | tasks from repos NOT among the 54 covered families (SWE-style bug-fix tasks from unused SWE-smith pools + harbor runs on public repos covered by sources.yaml rights) | 120 slots (60 tasks × 2 draws, T=0.7 — s12/s14 shape) |
| Q2 cross-domain probe | CI-workflow-family tasks from the registered `github-actions-public-ci` source (a genuinely distinct family axis, never blended into Q1 counts) | 10 tasks × 2 draws |
| Q3 thin-family reinforcement | optional: top thin families with ≥2 labeled rows, only if Q1+Q2 leave envelope headroom | ≤ 30 slots |

Q1/Q2/Q3 rows are labeled and reported SEPARATELY (campaign tags
`genfam-q1`, `genfam-q2`, `genfam-q3`) — family strata are never mixed before
measurement.

## Frozen choices

- **Author model (pinned)**: `MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reaso…bf16`
  — same author as S12/S14 (comparability; author is a first-class factor, S11).
- **Prompt/extract**: identical to the S12/S14 class (pilot_run.py chain —
  prompt, extraction, sanitize fix 3516b5e included). Any change = amendment.
- **Labeling**: the strict judge-free chain (image swe-smith → gold → patch →
  py_compile → F2P `-x -q` → P2P), quarantine cap 10% (LI-LABEL-001), rules v1
  byte-pinned. NO LLM judge in the labeling path (FR-9).
- **Promotion rule (v9)**: v8 + new rows satisfying applied ∧ compiles, labeled,
  y = 1 ⟺ f2p ∧ (p2p ok ∨ undeclared), dedup sha256(diff) against ALL of v8;
  state/gold taken from the task's base row (or task meta). Embedding:
  bit-identical S8 recipe (unixcoder-base CLS-512, incremental append-only
  order as in s14_pool).
- **Evaluation (pre-declared, gates unchanged)**: LOAO-strict with the v6
  reproduction control (must stay 0.822/0.779), per-family coverage table,
  family-LOAO on families with ≥ 5 rows (new statistic — reported, not gated),
  GxF strict + tail decomposition by provenance v8/q1/q2/q3. Gate v2 poles:
  NOT moved (no goalpost shift, ever).
- **What this window does NOT do**: no rerun of v8 rows; no geometry change to
  existing embeddings; no serving swap without the stage-2 flywheel protocol
  (disclosure + rollback).

## Budget envelope [ASSUMPTION — ratify at approval]

- Call cap: 350 model calls for Q1+Q2 (s14 spent 235 on 120 slots; budget
  ~2× margin for extraction retries post-sanitize-fix).
- Labeling window: one docker labeling session on the node, owner-supervised,
  deadline wall (autonomy_8h.sh pattern).
- Overspend behavior: stop at cap, record the shortfall as an amendment, never
  extend silently (S14 precedent: 251st in-flight call logged, not hidden).

## Abort & honesty rules

- Any quota producing > 60% no-diff after re-extraction → halt, diagnose
  (sanitize/extraction regression check), disclose in the addendum (S14
  precedent).
- Poison check: per-quota LOAO before mixing into v9; a quota measuring
  < 0.65 AUC ext-only stays OUT of v9 and is archived for study (S11 rule).
- Every row keeps provenance `{campaign: genfam-q*, author, window}` so strata
  remain separable forever (append-only pool discipline).

## Seal record (fill at ledger-anchoring ceremony)

- frozen_sha256: `a4732c9487a5033d734cd1f149ea5f9d0058c8eab9b4298da9d1de0ca6602495`
  — canonical identity lives in the prereg ledger (`data/release-store/prereg-ledger.jsonl`,
  row `type:"window-approved"`, anchored 2026-08-15T20:14:18Z), proof
  `data/release-store/proofs/window-a4732c9487a5033d.ots`, report
  `governance/act2/arm-artifacts/window-genfamilies-approval-report.json`.
  The digest covers this file's APPROVED-state bytes (this Seal section written
  afterwards as a pointer — no hash-in-file bootstrap, rct-prereg:159 /
  ladder-prereg:52 convention).
- ledger_chain: prereg ledger row `window-approved` (chain_hash = frozen_sha256)
  + OTS live anchor; verify per governance/prereg-ceremony.md.
- approved_by / envelope: Denis (owner), 2026-08-15 session — envelope as
  registered above approved unchanged (350 calls Q1+Q2; Q3 ≤30 only on
  headroom; overspend = stop-at-cap + amendment, never silent extension).
