# Act II pilot — phase report (2026-08-07, fenêtre complète 32 tâches)

Scope : les **32 tâches gelées** de `governance/act1-design/tasks-frozen.toml`
(FR-10, seed 6769) × 2 arms (off / on avec predictor advisory, seuil flip 0.5)
= 64 slots, 76 appels galere journalisés (`call-log.jsonl`). Modèle :
Qwen/Qwen3.6-35B-A3B-FP8. Harness sané (base = code post-injection-du-bug).

## Résultat net

Preuve : `data/landing/act2-pilot/results/*/meta.json` + `run-result.json`,
résumé machine dans `pilot-window-summary.json`.

| étage | off | on | total |
|---|---|---|---|
| diff applicable | 12 | 15 | 27 |
| py_compile ok | — | — | 24 |
| **F2P passent** | **4** | **5** | **9** |

Flip-probability (arm on, n=15 patchs appliqués — fenêtre v2 avec retry) :
- moyenne 0.622, médiane 0.612
- slots F2P-pass (n=5) : flip moyen 0.624
- slots F2P-fail (n=10) : flip moyen 0.620
- intervalle de séparation : **0.004 — pas de signal détectable**.
- Occurrence de l'hypothèse retenue : n=15 encore faible, mais la version « l'écart est caché dans peut-
  être » est réfutée sur ce panel ; le signal ERBVE du predictor, s'il existe, n'est pas publiable en l'état.

**Retry instrumenté (v2)** : 5 slots sauvés par le second essai (input = stdout git-apply du premier), les appels passent 64 → 121.
**Budget cumulé fenêtre** : 359 appels galere sur `call-log.jsonl`.

## Corrections méthodologiques (le pilote a servi à ça)

1. **`patch` des parquets swe-smith = commit qui INTRODUIT le bug.** Contrôle gold
   : les F2P passaient AVANT tout patch, échouent APRES. Runs sur base saine invalidés.
   Fixé dans `pilot_extract_buggy_src.py` + `pilot_node_exec.py`.
2. **Diffs LLM = toujours malformés** (compteurs @@, balises `</diff>`, contextes
   inventés). Pipeline : extract → sanitize → `git apply --recount` local → ré-export
   `git diff` natif propre. Le node ne reçoit que de l'applicable.
3. **Rejet des "full-file rewrites" qui résument** (< 50 % lignes d'origine).
4. **Split-site établi par mesure** : galere répond du Mac, jamais du node (401/403).

## Modèles passés en revue (même harness, même tâches)

| modèle | verdict mesuré |
|---|---|
| DeepSeek-V4-Flash | sur base saine : 3/8 applicables, 0/8 F2P |
| DeepSeek-V4-Flash-max | sur base saine : 5/8, 0/8 |
| GLM-5.2-NVFP4 / Kimi-K3 / gemma-4-31B / Nemotron-120B | timeout proxy 300 s — inutilisables sur ces contextes |
| **Qwen/Qwen3.6-35B-A3B-FP8** | **figé pour la campagne** (seul à respecter le timeout ET à produire des diffs opérationnels) |

## Ce que dit le pilote (n=64, honnêtement)

- Le taux de non-diff/inapplicable reste à **49/64 (~77 %)** — Qwen refuse ou
  hallucine ses contextes sur la majorité des bugs.
- Sur ce qu'il dépose : 7/21 (~33 %) passent les F2P. Mesure ERBVE effective
  liée au predictor : flip moyen 0.645 (succès) vs 0.607 (échec) — séparation
  non probante à cette taille, à ré-évaluer sur la campagne complète.
- Le bug pilote qui fit dérailler la session (ligne 42, `JOBS` vs `results/control-gold`)
  est documenté ci-dessus comme leçon : un contrôle gold + baseline avant TOUT
  chiffre publié est non-négociable.

## Suite immédiate validée

- Manifest : 32/32 tâches gelées résolues depuis le dataset SWE-bench/SWE-smith
  (shards HF, 32/32 trouvées), images pullées, états buggés confirmés (`buggy-state.json`).
- Budget : 238 / 2 000 appels galere consommés ce jour (162 + 76).
- Prochaine étape (à initier depuis ici) : passer de la fenêtre pilot (32) à la
  campagne pins-complète, flip vs F2P pass sur p inscriptible ≥ 0.05.

---

## Addendum 2026-08-07 — refit predictor sur les vrais artefacts (predictor-act2-v1)

Fenêtre 32-tasks × 2 arms × 2 tirages (v2 sans retry, v3 avec retry instrumenté) =
**50 patchs appliqués, 18 F2P-pass**.

**Validation sans leurre** (le point de la session) :

| protocol | accuracy | lecture |
|---|---|---|
| LOO pool 38 uniques | 0.895 (W95 0.76-0.96) | mémoire-task, inutilisable |
| train v2(n=27)→eval v3(n=23) | 1.000 | idem — cross-run = même tâche |
| **LOTO (leave-one-task-out, n=50)** | **0.66 vs majority 0.64, recall positifs 2/18** | **pas de signal cross-task** |

**Predictor-act2-v1 ne sépare succès d'échec que dans sa fenêtre d'entraînement.**
La marge mesurée n'est pas un signal généralisable de flip — c'est la trace que les
patchs d'une même tâche se ressemblent. La publication comportera ce graphe avec
sa mention "Ceci est une preuve négative publique".
