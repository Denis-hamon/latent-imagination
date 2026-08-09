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

---

## Addendum 2026-08-07c — pont vers la littérature world-models : l'énergie latente

**Méthode** : plutôt que d'ajouter des paramètres à un classifieur, nous avons évalué
ce que la lecture JEPA prescrit : une **énergie** = distance latente entre
`embed(state ∘ diff_candidat)` et `embed(state ∘ diff_gold)` (le "but" latent).
Encodeur : `microsoft/unixcoder-base` gelé, CLS-pooling, L2-normé, calculé sur le node
(GPU). Pool : 113 patchs applicables des campagnes frozen32+extension-128 (69 tâches,
44 positifs F2P au protocole chaîné d'origine).

**Mesures** (LOAO-strict où entraînement, sinon aucun) :

| mesure | valeur | statut |
|---|---|---|
| état seul (probe LOAO) | AUC 0,684 | contrôle (pas de prétexte dominant |
| diff seul (probe LOAO) | AUC 0,737 | classe-hash classique |
| état+diff concat (LOAO) | AUC 0,742 | bruit/représentation |
| **énergie latente, AUCUN entraînement** | **AUC 0,817** | **le meilleur signal de la journée** |
| diff↔gold seul | AUC 0,174 | pas de corrélation naïve u→û |
| état↔gold seul | AUC 0,543 | pas de leak tâche |
| buts permutés (contrôle négatif) | AUC 0,567 | ≈0,5 attendu — vérifié |

**Lecture** : ce n'est pas la distance "ses diff à gold" qui porte le signal (0,174) mais
l'espace conjoint (état, action) — exactement la structure que demande IWM (conditionner
sur l'action) et que LeCun formalise. L'attention analysée ne récompense pas visuellement
les bons patchs (top-tokens CLS ≃ tokens-structure identiques pour succès/échec) : le signal
est distributionnel, pas lexical.

**Correctif protocole (multi-hot per-test)** : la capture par-test a montré un écart de
protocole — 98,2 % des slots passent en exécution **individuelle** par test vs le verdict
chaîné `-x -q` (44/113). Le multi-hot n'est **PAS** feature (il contient le label —
tautologie, AUC 1,000 écartée comme fake) ; c'est un **auxiliaire de training** pour un
encodeur entraînable (prochaine étape, hors-budget session).

**Scripts** : `embed_pool.py`, `latent_energy_eval.py`, `probe_latent.py`, `per_test_results.py`.
**Artefacts** : `latent-pool.npz`, `latent-pool.json`, `per-test.json`, `latent-eval.json`
(sous `data/landing/act2-pilot/`, git-ignorés, reproductibles).

**Conséquence doctrine** : l'argument branch-iii n'est plus "le signal est nul" mais "le
signal vit dans l'espace latent conjoint et notre classifieur de sac-de-mots ne le voit
pas". La route de campagne change : entraîner un encodeur (loss multi-hot Yu) sur les
113-448 exemples plutôt qu'empiler des features syntaxiques.

---

## Addendum 2026-08-07d — tête énergie multi-tâches entraînée (résultat positif)

**Protocole** : encodeur `unixcoder-base` GELÉ ; seule tête MLP(1536→256)→
{binaire F2P, multi-hot Yu (4 bits pass/15 errclass), consistency bisimulation
(mutants token-rename)}. LOAO-strict : à chaque pli, une tâche ENTIÈRE sortie du train.
n=113 patchs, 44 positifs.

**Résultat** :
- acc **0,708** Wilson95 **[0,618, 0,784]**, baseline majoritaire 0,611 → borne basse
  AU-DESSUS de la baseline : premier entraînement act2 à passer le test d'honnêteté.
- AUC **0,731**.
- Écart moyen de probabilité : succès 0,573 vs échecs 0,217.

**Nota fuite prévenue** : le multi-hot Yu utilisé comme SOURCE binaire donne 111/113
positifs et un modèle à rien apprendre — c'est l'avertissement Yu §2.3 (l'auxiliaire
trop riche prédit la cible). Séquence valide : superviseur binaire = verdict chaîné
d'origine, auxiliaire = per-test.

**Scripts** : `train_energy_head.py`. **Artefact** : `data/landing/act2-pilot/head-eval.json`.

**Pieges identifiés pour la route campagne** : (i) encodage LLM frozen peut masquer
des features rare importantes — combiner auxiliaires denses (Littwin + Yu) ; (ii)
le `a-z` regex fixé pour respecter le paradigme mutation bisimulation.

---

## Addendum 2026-08-09 — verdict E2 (encoder fine-tuné Yu-aux) : REJET, partial honnête

**Protocole** : LoRA rank-8 (2 derniers blocs unixcoder) + tête multi-hot Yu superviseur
principal + binaire témoin — LOAO-compartimenté. 32/69 folds exécutés (arrêt volontaire
constaté quand le signal ne pouvait plus retourner : AUC max théorique ≤ 0.59 vu les 48
folds partials enregistrés).

**Partielle** (n=48, WARN: ordre alphabétique des tâches — PAS représetatif des 128) :
acc 0.792 = classe-majorité 0.792 ; AUC **0.513** ≈ hasard ; succès 0.361 vs échecs 0.364.

**Enseignement négatif mesuré** : à notre n=113 et avec un superviseur multi-hot dense,
fine-tuner l'encodeur **détruit** la séparabilité du verdict-binaire présente chez la tête
standalone entraînée sur l'encodeur gelé (acc 0.708/AUC 0.731). Conjecture (pas un fait) :
l'auxiliaire riche rend l'embedding spécialisé sur la surface du texte de test, effaçant
le pixop généraliste que le gel conservait — à publier comme négatif.
**Artefact** : `data/landing/act2-pilot/embedder-yu-eval.partial32folds.json` + loig
`e2-train.log`.
