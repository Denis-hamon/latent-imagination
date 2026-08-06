# Model strategy v1 — which model, and why (registered 2026-08-06, OQ-1 successor note)

Raised by Denis during Epic 4: *nowhere in the project is there research on using a strong
open model (Kimi K3-class, GLM-class, Qwen coder-class) to get materially better results
for the vibecoding pain points.* True. This note closes that gap — as a pre-registered
position, so a later arm or a detractor reads the SAME reasoning.

## 1. What is locked, and why (not laziness — instrument validity)

| Lock | Source | Reason |
|---|---|---|
| No LLM judge anywhere in the validity path | FR-9 | validity = the task's own F2P tests; a model verdict is un-auditable by design |
| Shipped mechanism computes in representation space, never token/narrated simulation | PRD glossary "Representation Space", §5.3 | doctrine, not cosmetics — a narrated sim reproduces the paradigm this module equips |
| Compute ceiling ≤ 2× L40S, gate p95 ≤ 1 s local, marginal cost ≈ 0 | NFR-C1, NFR-P1, FR-11 cost asymmetry (bar = 0.8889 from 0.02/0.0025) | a Kimi-K3-scale call per tool-call passes none of these |
| Contamination | Epic-2 controls + R2E-Gym stylistic-trap finding (caught by OUR pre-registered control, not by intuition) | any openly-pretrained coder has seen SWE-bench/SWE-smith-class corpora; its "prediction" on them is unmeasurable by our instrument without the controls we built |

So the **detector** stays bespoke and small — that is not under-researched, it is the claim.

## 2. The option matrix (what the critique actually changes)

| Option | Doctrine | Verdict |
|---|---|---|
| A. Strong open model EMITS the gate verdict (Kimi K3 / GLM / Qwen endpoint) | violates FR-9 + representation-space lock + latency/cost; contamination makes its demo numbers unverifiable | **REJECTED, with reasons** — not "rejected because weak" |
| B. Current arms only (boring baseline / JEPA-lineage), more + better FLIP data (Epic-3 retro growth path) | conformant | **KEPT for this cycle** — verdict stands: branch (iii), "more data, NOT another arm" |
| C. **Frozen open-coder ENCODER + downstream calibrated head** (best-available checkpoint among Qwen-Coder / GLM / Kimi families at selection time; embeddings frozen; head = our measured pipeline) | conformant — the boring baseline already IS "features → head"; upgrading the encoder upgrades capacity without touching validity | **REGISTERED as the first candidate arm of the NEXT probe cycle** (after corpus floor closes). Pre-registered selection rule: the encoder is chosen by Act-I family ERBVE coverage + published eval cleanliness, swapped by amendment only |
| D. Own pretraining on the Noisy Tier (~10⁷) | conformant | long-term; needs the Epic-4 harvest at scale |

What would change our mind on A: published contamination-resistant evaluation of such a
model on our task class AND per-call cost/latency fitting the gate envelope. Neither exists
as of 2026-08-06 (checked during this note).

## 3. Immediate, in-scope wins from the critique

- **Measure those families, don't ship them**: Kimi-K3 (already reachable via the builder's
  OpenAI-compatible endpoint → `scripts/act1/live_agent.py`), GLM and Qwen generated
  trajectories enter as declared trace sources in the NEXT field-measurement window, so Act I
  reports ERBVE per generation incl. those families, and Epic-8's ranking gets real rows.
- **Encoder bake-off budget**: at next probe kickoff, the frozen-encoder candidates are
  evaluated as the FEATURE extractor under the same pre-registered protocol (same splits,
  same bar, same controls). No marketing wins — only the sealed protocol arbitrates..

## 4. Amendments

New cycle, new version (`model-strategy-v2.md`); this file is append-only.
