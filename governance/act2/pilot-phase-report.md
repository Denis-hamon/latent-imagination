# Act II pilot — phase report final (2026-08-07)

Scope : panel gelé 32 tâches (FR-10, seed 6769) + extension 128 tâches (seed même).
Modèle : Qwen/Qwen3.6-35B-A3B-FP8. Endpoint : galere (split-site Mac/node).
Harness sané : bug-injection préalable contrôlée (`control-gold` + `control-baseline`).

## Budget consolé

| fenêtre | appels galere |
|---|---|
| relances debug + ladder modèles (DeepSeek/GLM/Kimi/Qwen…) | 162 |
| fenêtre gelée 32 tâches (v1+v2+retry) | 76+121+123 = 320 |
| extension 128 tâches | 490 |
| **total consommé** | **972 / 2000 cap jour** |

Toutes les lignes sont dans `data/landing/act2-pilot/call-log.jsonl` et
`extension-128/call-log.jsonl`.

## Application & build — toutes fenêtres

| fenêtre | slots | diff applicables | compilent | F2P passent |
|---|---|---|---|---|
| gelée 32-tâches × 2 arms (3 tirages) | 3×64 | 24, 27, 26 | —, 24, 24 | 7, 9, 9 |
| extension 128-tâches × 2 arms | 256 | 90 | 77 | 35 |
| **pooled** | **448** | **167 (37 %)** | **125 (28 %)** | **59 (13 %)** |

Reproductibilité gelée : re-tirages du même panneau donnent 7→9→9 F2P-pass à 88 %
d'agrégation par tâche — la variabilité est de l'ordre du bruit modèle,
pas de la mesure.

## Predictor — lecture consolidée

| window | n slots `on` applicables | flip succès | flip échecs | Δ |
|---|---|---|---|---|
| v2 (sans retry) | 12 | 0.645 | 0.607 | +0.038 |
| v3 (avec retry) | 15 | 0.624 | 0.620 | +0.004 |
| extension 128 | 42 | 0.624 | 0.595 | +0.030 |
| **pooled** | **69** | 0.6224 | 0.5992 | **+0.0232** |

**Verdict** : le predictor actuel ne sépare pas signifant succès vs échec sur les
diffs applicables. Δ ~ 0.02–0.04 à n=69 — en deçà du seuil publiable.
Conséquence : la campagne doit soit retraire le predictor sur les vrais patchs
couplés du panel (act2-v1 ci-dessous), soit déclarer l'arm-on neutre dans la publication.

## Refit act2-v1 sur les vrais artefacts

- Pool : 38 patchs uniques de la fenêtre gelée (LOO 89.5 %, Wilson95 [75.9,95.8])
- **MAIS** — honnêteté méthodologique, non sous le tapis : ce 0.895 est
  **in-sample optimistic**. Même patch-family (mémo tâche) peut fuiter entre plis.
  La cross-éval passage-vraie (LOAO-LOTO sur 50 slots) donne **66 %, recall positifs 11 %**
  — plus honnête mais faible en cercles de taille n≈30.
- Conclusion : act2-v1 LOO-optimiste, LOTO-honnête. Ne pas l'utiliser comme seuil
  de campagne avant 200+ patchs labelisés.

## Leçons méthodologiques acquises (pilote utile)

1. `patch` dans les parquets swe-smith = commit d'injection du bug — le contrôle gold est
   NON-négociable avant tout chiffre.
2. Les diffs LLM sont **toujours malformés par défaut** — sanitize→recount→reexport est
   la procédure canonique, `git apply` local avant node.
3. garde-fou "whole file" (si réponse < 50 % lignes → rejet) : à garder, sinon le modèle
   résume.
4. Retry instrumenté (stderr git-apply → prompt) récupère ~5 slots/64 en un appel.
5. **Séparer "applique/compile/F2P" et vérifier P2P pour chaque succès déclaré**
   (un vrai fix fait passer F2P ET ne casse pas P2P) — les 9 succès gelés récents P2P verts.
6. Split-site galere est un fait mesuré.

## État call-stack jour

Constatation complète : fenêtres gelée + extension déposées, toutes mesures journalisées
(5928 events en fichiers JSON natifs, tables propres). Suite : passage aux patches générés
honnêtement en "campaign-pins-v2.json" → remplir machinerie gallagate (cf. FR-6).

---

## Addendum 2026-08-07b — refit act2-v2 (pool unifié, LOTO)

**Pool** : 111 patchs applicables, dédupliqués (tâche, diff) — frozen32 3 fenêtres + extension-128 — 41 positifs (F2P-pass), 71 tâches distinctes.

**Éval leave-one-task-out (le seul protocole qui prouve la généralisation)** :

| métrique | act2-v2 (n=111, 71 tâches) |
|---|---|
| accuracy | 0.676 (Wilson95 [0.584, 0.756]) |
| baseline majoritaire | 0.631 |
| recall positifs | 34 % (14/41) |
| précision positifs | 61 % (14/23 annoncés) |
| score_gap (succès−échecs) | +0.127 |
| confusion | TP=14 FP=9 FN=27 TN=61 |

**Lecture** : le score gap existe et n'est plus dans le bruit nul (v0 : +0.023 → v2 : +0.127), mais l'accuracy LOTO reste dans l'overlap de la baseline majoritaire.
**Verdict** : predictor-act2-v2 = advisory mesuré (pas un instrument certifié). Doctrine branch-iii confirmée, on ne passe pas sub-bar → certified.

**Fichier** : `governance/act2/arm-artifacts/predictor-act2-v2.json` (sha256 `0a0604e06d78625e`, pinned).
