# A World Model of Software, Measured

**Latent-energy prediction of test outcomes for machine-written patches —
first JEPA-style probe on code with executable tests as ground truth.**

Denis Hamon — latent-imagination project — 2026-08-10
Artefact of the Act II campaign; every number below reproduces from this
repository (`scripts/act2/e*.py`, artefacts under `data/landing/act2-pilot/`).

---

## Abstract

World-model methods (JEPA family) predict in representation space, but every
published instance learns on pixels, video or text — modalities whose labels are
slow, fuzzy or judge-dependent. Source code with executable tests is the one
modality where the ground truth of an action's consequence is instant, binary
and judge-free: the patch's own fail-to-pass tests.

We measured whether the JEPA prescription — an *energy* in latent space — carries
the signal "this patch makes the tests pass", at the harsh end of the data regime
(n=113 patches, 69 tasks). It does: an *untrained* energy over frozen uniXCoder
embeddings reaches **AUC 0.817**, an honesty-respecting leave-one-task-out
accuracy of **0.735 [0.646, 0.807]** against a 0.611 majority baseline. We then
ran the six refinements the literature prescribes and measured every one:
three clean ties (discrete vs Gaussian latents; bisimulation auxiliary; dense
Yu-style auxiliary), one question shown unaskable at our granularity
(hierarchical macro-actions; our diffs are 95 % single-hunk), one rejection
guide-rail confirmed (fine-tuning the encoder on the rich supervisor *destroys*
separability, AUC 0.513), and one conceptual finding: **the goal-conditioned
value metric (Destrade-style expectile) and the bisimulation metric (Toso-style)
are orthogonal axes on real data** (Spearman ρ ∈ [−0.10, −0.04], Fisher CI
squeezing 0) — two papers the field implicitly merges measure different things.

We publish the instrument, the negatives, and the ties. The strongest claim we
allow ourselves: an *advisory* gate, already live as an MCP server; never a
certified predictor.

## 1. Setting

| | |
|---|---|
| Pool | 113 applicable LLM-written patches, 69 tasks, 44 F2P-positives (38.9 %) |
| Tasks | swe-smith injected bugs (frozen 32-task panel + 128-task extension, seed 6769) |
| Candidate author | Qwen3.6-35B-A3B-FP8 (galere endpoint), apply-retry harness |
| Label | each task's own fail-to-pass tests, chained protocol, gold-control validated |
| Encoder | `microsoft/unixcoder-base`, frozen, CLS, L2-normalised |
| Energy | `1 − cos( norm(E_state+E_diff), norm(E_state+E_gold) )` |

The naive predictor (syntax features + GBDT) saturates at 0.676 [0.584, 0.756] —
inside baseline overlap. The latent formulation is where the signal lives.

## 2. Protocol honesty (the claims you can check)

- **LOAO-strict**: one *entire task* held out per fold; thresholds relearned on
  train only (median-energy rule, one hyperparameter).
- Paired comparisons throughout: McNemar exact on per-sample discordances.
- Wilson 95 % CIs next to every accuracy; majority baseline always printed.
- Every negative published with its artefact, same file layout as the positives.
- Pre-registered spend posture (R10); this campaign consumed **zero** endpoint
  calls — all six studies run on the frozen pool.

## 3. Results — the ten verdicts

| # | study | result | status |
|---|---|---|---|
| 1 | Latent energy, **no training** | AUC **0.817** (controls: state 0.684, diff 0.737, permuted-goal 0.567) | **positive** |
| 2 | Multi-task energy head (frozen encoder) | LOAO acc **0.708** [0.618, 0.784], AUC 0.731 | **positive** |
| 3 | Goal-conditioned critic (Destrade), median rule | LOAO acc **0.735** [0.646, 0.807], E_succ 0.011 vs E_fail 0.040 | **positive** |
| 4 | Encoder fine-tune on rich supervisor (LoRA) | AUC 0.513 ≈ chance | **rejected** |
| 5 | Boltzmann energy-guided sampling, K=4/task | 1/32 vs 1/32 random | **honest NO** |
| 6 | Discrete (Bernoulli) vs continuous latent — LeCun §4.2 vs Var-JEPA | 1-bit 0.743 / 2-bit 0.752 vs 0.735, McNemar p=1.0 / 0.754 | clean tie |
| 7 | Bisimulation auxiliary (token-rename mutants), isolated | 0.717 vs 0.726 without, p=1.0 | clean tie |
| 8 | Dense per-test auxiliary (Yu), isolated | 0.726 vs 0.726, zero discordant pairs | clean tie |
| 9 | Hierarchical macro-action (hunks → intention) | pool is 95 % single-hunk; macro 0.761 vs flat 0.735, p=0.55 | unaskable here |
| 10 | **Expectile metric ≈ bisimulation metric?** | Spearman **−0.10** [−0.28, +0.08] (τ=0.9), −0.04 (τ=0.5) | **orthogonal** |

## 4. What this means (and what it does not)

**The landscape is real.** Three independent reads — untrained energy, trained
head, goal-conditioned critic — clear the majority baseline with Wilson lower
bounds above it, on a protocol built to kill leakage. The latent geometry of a
frozen code encoder already separates "tests will pass" from "they won't",
*without ever seeing a label* (study 1).

**But the landscape is a risk measure, not a steering wheel.** At decision time
(pick 1 of K=4 candidates), energy-guided sampling ties with random (study 5).
Population-level ranking power does not imply point-wise selection power; the
gap between the two *is* the paper.

**Two metric families the literature treats as one are empirically disjoint on
our data.** Destrade's goal-conditioned value distance and Toso's bisimulation
distance each correlate with the outcome — and not with each other (study 10).
An objective fusing them is not supported; claim it per-axis or not at all.

**The LeCun-vs-Var-JEPA contradiction (discrete vs Gaussian z) is empirically
mute at our scale**: 1-bit quantisation preserves accuracy point-for-point
(study 6). Either both formalisms survive contact with code latents, or our n
cannot hear the difference — we report which.

## 5. Limitations (the section we write first)

1. n=113 patches / 69 tasks; every CI is wide, by construction visible.
2. Diffs are 95 % single-hunk: hierarchy, planning and multi-step structure
   cannot be measured on this pool (study 9 shows the question failing, not the
   hypothesis).
3. One candidate LLM family, one encoder, injected-bug distribution ≠ organic
   bug distribution.
4. AUC 0.817 → deployment-grade separation is a gap we do not cross; the MCP
   gate is advisory, logged, and nightly-recalibrated for exactly that reason.

## 6. Reproduce

```bash
# frozen pool + embeddings are git-ignored data artefacts; regen via scripts/act2/
uv run --no-project --with numpy python scripts/act2/e2_discrete_latent.py
uv run --no-project --with torch,transformers,numpy python scripts/act2/e6_aux_ablation.py
uv run --no-project --with torch,transformers,numpy python scripts/act2/e5_iql_vs_bisim.py
uv run --no-project --with torch,transformers,numpy python scripts/act2/e3_macro_action.py
```

Corpus release v0: https://doi.org/10.5281/zenodo.21837153 —
mirrors on HF `denishamon/latent-imagination-releases`.
Deployment artefact: `scripts/mcp/energy_gate_server.py`
(calibration `governance/act2/arm-artifacts/predictor-mcp-calibration.json`).

Full audit trail (ten addenda, French): `governance/act2/pilot-phase-report.md`.
