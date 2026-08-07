# Act II campaign plan v1 (story 6.1)

**What this story built:** the pins machinery (`probe.campaign`) — `campaign-pins-v1.json`
aggregates: the Act I design + task set (byte-identical, hash-cited), agents with
evidence-backed versions (a pin without an evidence file fails the build, LI-PROBE-003),
the ≥3-family floor enforced (FR-6), and the module slot.

**Doctrine translation (branch iii, decided 2026-08-06):** the module IS the advisory
baseline — measured, NEVER certified. Run manifests refuse a `pending-reexport` pin;
re-export via `probe.arms.baseline_export` is the window-proximity step.

**Execution window (owner-run, R10 pre-registered spend posture):**
1. Re-export baseline → fills the module pin (hash becomes real).
2. Node campaign: harbor-driver runs, module enabled/disabled arms, same tasks.
3. API vendors that drifted since Act I pins → un-augmented arm re-collected alongside;
   drift disclosed in the paired publication (FR-10 machinery is in the pins).
4. Open-family extension (per model-strategy-v1 §3): Kimi/GLM/Qwen trajectories are
   admissible pin entries with their own evidence files.

**`campaign-pins-v1.json` is deliberately NOT minted yet** (2026-08-06): the builder
fail-closed on the live attempt — Act I's field measurement evidences two families
(claude, openai) and FR-6 requires three. The third arrives WITH its evidence file at
the window (step 4). A pins file minted on a placeholder family would be counterfeit —
the machinery saying no, on the record, is the system working.

**Sealed-amendment discipline:** any change to pins/design mid-window = an amendment
(same machinery as the sealed envelope: logged BEFORE outcomes, hash-referenced).
**The refusal gates (`require_module_pin`, `require_task_set`) wire into the run
manifest at campaign-run assembly (window step) — present-tense refusal begins then.**

**Budget note (R10):** the campaign spend ceiling belongs to the window's pre-registration
(step before ANY paid run), same posture as the 4.1 harvest caps.

## Family-3 pilot evidence (2026-08-07)

- Endpoint galere (`https://ai.galere.org/v1`, opencode provider) reachable sans clé; first
  recorded attempt: `family3-pilot/kimi-k3-boltons-c1c25da-attempt0.json` —
  model `moonshotai/Kimi-K3`, task `boltons/mathutils.py` fix commit `c1c25da…`,
  outcome: **false start** (patch_applied=false, flipped=false — valeur honnête, c'était
  le jour 1 du endpoint), wall 94 s, 2 167 tokens.
- 1 / 2 000 calls consommés (usage_log in budget-v1.toml). La série complète
  (≥50 tâches) passe par la fenêtre node, pas par un laptop.
