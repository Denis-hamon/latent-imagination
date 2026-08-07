# Act II pilot — phase report (2026-08-07)

Scope : 4 tâches swe-smith avec image docker (agronholm/exceptiongroup,
mahmoud/boltons, oauthlib/oauthlib, pygments/pygments) × 2 arms (off / on avec
predictor advisory, seuil flip 0.5). Appels galere journalisés : **162**
(`data/landing/act2-pilot/call-log.jsonl`, dont ~10 dans le run final exploitable).

## Résultat mesuré — run final valide (base = code buggé, modèle Qwen3.6-35B-FP8)

| tâche | arm | patch | applique | py_compile | F2P passé | flip_pred |
|---|---|---|---|---|---|---|
| agronholm__exceptiongroup.0b4f4937 | off | ✓ | ✓ | ✓ | **✓** | — |
| agronholm__exceptiongroup.0b4f4937 | on  | ✓ | ✓ | ✓ | **✓** | 0.73 |
| mahmoud__boltons.3bfcfdd0 | off/on | ✗ (inapplicable / pas de diff) | — | — | — | — |
| oauthlib__oauthlib.1fd52536 | off/on | ✗ (inapplicable) | — | — | — | — |
| pygments__pygments.27649ebb | off/on | ✗ (pas de diff) | — | — | — | — |

Preuves : `results/*/run-result.json`, `buggy-state.json`, `model-ladder.jsonl`.

## Corrections méthodologiques apprises (pilote = à ça sert)

1. **La colonne `patch` des parquets swe-smith est l'injection du bug, pas le fix.**
   Le contrôle positif gold l'a prouvé : F2P passent AVANT tout patch, échouent après.
   Tout run sur la base non-buggée mesure du vent. Corrigé dans
   `scripts/act2/pilot_extract_buggy_src.py` (extraction post-injection) et propagé à
   `pilot_node_exec.py` (bug appliqué avant le patch agent).
2. **Les diffs LLM sont syntaxiquement malformés par défaut** (compteurs @@ inventés,
   balises `</diff>`, contextes hallucinés). Pipeline d'assainissement dans
   `pilot_run.py` : extract → sanitize → `git apply --recount` local → ré-export
   `git diff` propre. Le node ne reçoit plus que des diffs applicables.
3. **Contrôle-fou ajouté sur les "full-file rewrites"** : rejeter si la réponse fait
   < 50 % des lignes d'origine (le modèle résume au lieu de réécrire).
4. **Split-site confirmé** : galere répond UNIQUEMENT depuis le Mac (UA curl /
   opencode), jamais depuis le node (401/403). Le modèle reste côté Mac, docker côté node.

## Modèles évalués (même harness, même budget)

| modèle | behaviour mesuré |
|---|---|
| DeepSeek-V4-Flash | base saine → 3/8 diffs applicables, 0/8 F2P |
| DeepSeek-V4-Flash-max | base saine → 5/8 applicables, 0/8 F2P |
| GLM-5.2-NVFP4 / Kimi-K3 / gemma-4-31B / Nemotron-120B | timeout proxy 300 s sur source ≥ ~1000 lignes — **inutilisables** tels quels |
| **Qwen/Qwen3.6-35B-A3B-FP8** | base buggée → **2/8 F2P passés** (les seuls) |

## Lecture scientifique (honnête, n=4 tâches)

- Le flip-probability du predictor (0.73 sur l'arm `on` d'exceptiongroup) coïncide
  ici avec un succès F2P ; avec 4 tâches c'est anecdotique, pas calibré. La campagne
  doit chiffrer ce lien sur des centaines de tâches.
- Le taux d'échec format (75 % de non-patch) chez Qwen3.6 sur base buggée réelle
  est un signal ERBVE propre : l'agent produit volontiers du diff sur un théâtre
  sain, moins sur un vrai bug.
- Aucun chiffre publié ne concerne la base saine — ces runs étaient une mesure
  d'harness, pas d'agent.

## Pour la campagne

- Modèle porteur validé : **Qwen/Qwen3.6-35B-A3B-FP8** (seul sous timeout proxy).
- Harness figé : extraction source post-bug + validation locale `git apply --recount`.
- Étendre les 4 tâches → le panel complet des images swe-smith disponibles.
- Critère publique : flip-prob vs F2P-pass sur patchs applicables, désormais mesurable.
