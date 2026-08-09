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

---

## Addendum 2026-08-09b — E4 Destrade critic : paysage mesuré, marche réelle

**Protocole** : distance latente `1 − cos(state+diff, state+gold)` par uniXCoder figé,
LOAO par tâche, seuil = médiane train (un seul hyperparam, appris à chaque fold).

**Résultat** : n=113, LOAO acc **0.735** Wilson95 **[0.646,0.807]** vs maj 0.611 — borne basse
au-dessus de la baseline. **AUC 0.817** identique au probe non-entraîné (la secular louds
le même paysage). Distances latentes : succès moy `0.011`, échecs moy `0.040` (~4×)
— l'énergie n'est pas binaire-able à l'espoir, elle quadrit.

**Ce qu'on a gagné** : l'objet "world model" n'est plus un classif — c'est une métrique
dans un espace qu'on peut marcher (CEM/MPPI carrhugement). Le fixed pointe "le plus proche
du but en distance latente" mérite E1. Artefact : `e4-critic-eval.json`.

---

## Addendum 2026-08-09c — E1 boltzmann-échantillonneur : égalité propre (rejet)

**Protocole** : 32 tâches gelées × 4 candidats modèle à T=0.7 → encodeur (uniXCoder
gelé) → sélection = argmin énergie latente (1 − cos(state+diff, state+gold)) vs
sélection = uniforme — même harness docker, même gold-apply, F2P mesuré.

**Résultat** : théorie **1/32** F2P-pass | random **1/32**. Les deux succès sont sur
des tâches distinctes (getmoto vs feedparser) — pas de biais de difficulté évitée.

**Interprétation honnête** : l'énergie mesure 0.817-AUC sur le pool observé (état,diff),
mais au point de décision "lequel de ces 4 cracha va passer" elle ne départage **pas
mieux que le hasard** à n=32. C'est la limite de l'objet sans entraînement : la distance
latente est informative au sens populationnel (LOAO) mais pas en choix discret par tâche
avec K=4 voisins. Pour marcher, il faut soit un ε-greedy learné de la table d'énergie,
soit un scorer affiné sur P(traj complet) — ni l'un ni l'autre n'est aujourd'hui à portée
de 24 h runtime restant. **Conclusion : tout l'exploit ici est dans "avoir une mesure de
risque au niveau population", pas "guider le choix ponctuel" — publier ce NON.**

---

## Addendum 2026-08-10 — clôture des 6 pistes « haute voltige » (synthèse WMM §3)

**Collision de numérotation, d'abord** : les addenda 08-09 ont réutilisé les labels E1/E2/E4
pour boltzmann/Yu-aux/Destrade. Ci-dessous, « E1…E6 » désignent les **pistes du document de
synthèse** (`docs/literature-synthesis-wmm.md` §3) — les seules que ces addenda clôturent.

Pool commun aux 5 expériences : 113 patchs, 69 tâches, LOAO-strict, embeddings uniXCoder
gelés (`latent-pool.npz`), même règle de seuil médiane-train. Tout calculé localement
(encodeur en cache HF, CPU) — zéro appel galere consommé.

### E1-synthèse — mutation-syntax comme supervision bisimulation : **égalité propre**

Contraste isolé à tête et init identiques, LOAO apparié : binaire seul **0.726**
[0.637,0.799] vs binaire + λ·L_bisim (mutants token-rename, λ=0.3) **0.717** — McNemar
b=5/c=4, p=1.0. AUC 0.749→0.759 (n.s.). Le terme bisimulation, noyé dans la loss à 3
composantes du 08-07d, n'y portait rien de mesurable non plus. **Verdict : à n=113, la
supervision par mutants syntaxiques n'ajoute ni ne retire — Toso non infirmé, non confirmé.**

### E2-synthèse — latent Bernoulli vs gaussien : **égalité propre (contradiction littérature non tranchée)**

Même composition E4, seule la nature de z change : continu **0.735** [0.646,0.807]
(reproduction exacte du contrôle publié) ; 1-bit médiane-train **0.743** (McNemar p=1.0) ;
2-bit quartiles **0.752** (p=0.754). AUC 0.817 → 0.801/0.815. **Verdict : discrétiser ne
détruit pas le signal à n=113 — le débat LeCun §4.2 (z discret) vs Var-JEPA (z gaussien)
est empiriquement muet sur notre modalité à ce régime.**

### E3-synthèse — macro-action hiérarchique : **irrecevable sur ce pool (mesuré)**

Les actions du pool sont mono-hunk à 95 % (médiane 1, max 2) : la hiérarchie dégénère en
lecture plate. Mean-pool d'hunks : 0.761 vs flat 0.735 (p=0.549, n.s.) ; bottom-only
0.611 = majorité (AUC 0.722 résiduelle). **Verdict : la question HWM-sur-code exige des
diffs multi-étapes ; notre pool ne les fournit pas. À reposer sur corpus de PR multi-commits.**

### E5-synthèse — métrique expectile (Destrade) ≈ métrique bisimulation (Toso) ? : **orthogonalité mesurée**

d_IQL (−V̂ expectile τ=0.9, LOAO) sépare y proprement (AUC 0.737) ; d_bisim (couplage
mutants) faiblement (succ 0.184 vs fail 0.173, AUC 0.600 — les *succès* se couplent
davantage à la surface, contresens noté sans l'embellir). Et Spearman(d_IQL, d_bisim) = **−0.10**
(τ=0.9) / **−0.04** (τ=0.5), IC95 Fisher ⊂ [−0.28, +0.15]. **Verdict : deux axes
orthogonaux à n=113 — le pont « objectif fusionné Destrade × Toso » n'est PAS supporté
par nos données. C'est le résultat de pont le plus net de la session : les deux papiers
peuvent être vrais chacun sans jamais parler de la même chose.**

### E6-synthèse — auxiliaire multi-graine vs binaire : **égalité propre**

Binaire seul vs binaire + multi-hot Yu (4 bits + 15 errclass) : **0.726 / 0.726**, McNemar
0 discordance sur 113, AUC +0.003. **Verdict : l'enrichissement Yu est neutre à ce régime ;
le garde-fou de l'addendum 08-07d (aux-trop-riche → tautologie) reste la leçon active.**

### Bilan campagne

| piste | verdict | chiffre clé |
|---|---|---|
| énergie latente no-train (08-07c) | **positif** | AUC 0.817 |
| tête énergie multi-tâches (08-07d) | **positif** | LOAO 0.708 |
| Yu fine-tune encodeur (08-09) | **rejet** | AUC 0.513 |
| Destrade critic (08-09b) | **positif** | LOAO 0.735 |
| boltzmann sampler (08-09c) | **NON honnête** | 1/32 = 1/32 |
| E1 bisim isolée | égalité | p=1.0 |
| E2 discret vs gaussien | égalité | 0.743/0.752 vs 0.735 |
| E3 macro-action | irrecevable ici | mono-hunk 95 % |
| E5 IQL vs bisim | **orthogonalité** | ρ≈−0.1, CI serre 0 |
| E6 aux dense | égalité | p=1.0 |

Lecture doctrine : le paysage latent porte le verdict (3 positifs convergents), mais aucune
des cinq « raffinements de haute voltige » issus de la littérature ne le modifie à n=113 —
et E5 montre qu'au moins deux familles de papiers y mesurent des choses **différentes**.
Scripts : `e2_discrete_latent.py`, `e6_aux_ablation.py`, `e5_iql_vs_bisim.py`,
`e3_macro_action.py`. Artefacts : `data/landing/act2-pilot/e{2,3,5,6}-*.json` (git-ignorés,
reproductibles). Piste E4-synthèse (le texte « World Model of Software ») : **rédigé** —
`docs/world-model-of-software-e4.md`, construit sur les 10 addenda de ce rapport.
