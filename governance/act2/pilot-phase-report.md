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

---

## Addendum 2026-08-10b — G1 goal-free : l'énergie est goal-bound, les échecs parlent seuls

**Contexte** : tout usage production (MCP live) se fait SANS gold. Gate de validité
mesurée sur le pool (LOAO-strict, seuil médiane-train par fold) :

| score | AUC | acc LOAO |
|---|---|---|
| GOLD (contrôle) | 0.817 | 0.735 [0.646,0.807] |
| but retrievé 1-NN (R1) | 0.556 | 0.540 — **mort** (McNemar p=0.005 vs GOLD) |
| buts top-3 moyens (R3) | 0.578 | 0.566 |
| **failure-attractor (F1)** | **0.709** | 0.637 [0.545,0.720] |
| vote k-NN vanilla (K5V) | 0.667 | 0.593 |
| buts permutés (contrôle) | 0.479 | 0.478 ✓ protocole |

Spearman(GOLD, F1) = **+0.187** (presque orthogonaux) ; rang-moyen GOLD+F1 = **AUC 0.838**.

**Verdict** : (i) la destination spécifique porte l'information, un but emprunté ne
transfère pas ; (ii) la distance aux échecs passés est un signal autonome, qui bat le
retrieval vanilla (+0.042 AUC) ; (iii) l'instrument production = **deux axes**
(direction-vers-but où le but existe / répulsion-des-échecs partout).
Conséquence produit et plan RCT pré-enregistré (A/B agent ± contexte-conséquence) :
`docs/world-model-mcp-design.md`. Script : `g1_goal_free_energy.py`.
Artefact : `data/landing/act2-pilot/g1-goal-free.json`. Zéro appel galere consommé.

---

## Addendum 2026-08-10c — RCT « consequence-context » : NÉGATIF honnête (pré-enregistré, 5 amendements scellés OTS)

**Question** (rct-prereg-v1, chaîne dae108b1→a0a5ec3d ancrée OpenTimestamps) :
un bloc contexte-conséquence world-model (attracteur F1 + near-miss outcomes, sans
gold) injecté à la régénération améliore-t-il le F2P ?

**Protocole exécuté** : fork apparié du draft draw-3 par tâche (frozen 32) —
b0 = régénération neutre, b1 = même fork + bloc WM ; modèles : Qwen3.6-35B (48 premiers
slots) puis substitut roster MLX-Qwen3.5-35B (16 derniers) — co-modèle garanti par
paire tâche. Fenêtres 1-3 écartées (bugs extraction découverts et documentés dans les
amendements : premier-bloc-fenced, troncature ligne-vide, hunks alignés sur version
upstream mémorisée) — spend debug 65 calls R10 séparé. Série : arrêt exact au **cap 100**.

**Résultat primaire — ITT (slot sans candidat = échec), n=32 tâches** :

| arm | F2P | vs |
|---|---|---|
| A (draft seul) | 4/32 = 0.125 | — |
| B0 (regen neutre) | 3/32 = 0.094 | vs A : p=1.0 |
| B1 (regen + contexte WM) | 2/32 = 0.062 | vs B0 : p=1.0 ; vs A : p=0.5 |

Sensibilité complete-case (12 paires où les deux arms ont produit) : B0 0.250 vs
B1 0.167, p=1.0.

**Verdict** : pas d'effet détectable du contexte WM à n=32 ; l'estimation ponctuelle
est **négative** (la régénération elle-même dégrade légèrement, conforme au diagnostic
d'amendement 3 : la régénération rouvre la porte à la version upstream mémorisée).
Sous-puissance assumée (discordances 0-2 par comparaison) — mais publier un négatif
scellé était le plan B explicite du prereg, et il tient. **Le RCT ne soutient PAS la
claim « le contexte world-model améliore le F2P du LLM » à ce régime.**

**Sous-groupes modèle** (dette de l'amendement 5, soldée ici ; borne = crash roster) :

| sous-groupe | arm | slots | candidats | F2P mesurés |
|---|---|---|---|---|
| Qwen3.6-35B (38 slots) | b0 | 19 | 9 | 1/7 |
| | b1 | 19 | 8 | 0/5 |
| Qwen3.5-35B-distillé (24 slots) | b0 | 12 | 5 | 2/4 |
| | b1 | 12 | 6 | 2/5 |

Lecture : production de candidats à **parité stricte** entre arms (14/31 vs 14/31)
— rectificatif à une observation de mi-fenêtre qui suggérait une dégradation b1 ;
la différence se niche uniquement dans la conversion F2P (3 vs 2, n.s.).
Le sous-groupe 3.5-distillé convertit mieux que 3.6 (4/9 vs 1/12) — descriptif
seulement, n très faibles, aucune conclusion de modèle.

Leçons : (i) l'ITT reste indispensable — 34/62 slots sans candidat (parité arms) ;
(ii) la claim viability du MCP repose désormais sur l'axe évaluation/infrastructure
(jamais réfuté), pas sur l'augmentation directe.

Artefacts : `rct-v1/analysis.json`, `rct-v1/results/`, 4 chaînes ancrées
`data/release-store/chains/`. Logs : `rct-v1/call-log.jsonl` (100) +
`discarded-window-{1,2,3}/` (65).

---

## Addendum 2026-08-10d — ladder-v1 annulée par budget, findings harness + transparence de dépense

**Contexte** : après le RCT négatif, la question « performances absolues adéquates »
exigeait une ladder 2 modèles récents (DeepSeek-V4-Flash-max, GLM-5.2-NVFP4) sur le
même panel gelé (ladder-prereg-v1, 2 amendements). **Décision owner 2026-08-10 :
STOP NET — l'enveloppe R10 (cap 2000 galere/projets) est quasi épuisée (~28 calls
libres)** ; aucune extension votée. La série est annulée **avant tout résultat F2P**.

**Spend du jour (audit complet, budget-v1.toml)** :

| poste | calls |
|---|---|
| série RCT publiée (cap 100, arrêtée exactement au cap) | 100 |
| debug protocolaire RCT (3 fenêtres écartées + diagnostics) | 65 |
| ladder fenêtre 1 (extraction 1er-bloc inadaptée aux modèles à raisonnement) | 17 |
| ladder fenêtre 2 (extraction réparée mais plafond tokens) | 37 |
| **total jour** | **219** |

**Findings harness à consigner** (valeur durable, au-delà de la série annulée) :

1. `extract_diff` ne capturait que le 1er bloc fenced — les modèles à traces de
   raisonnement en émettent 20-50 → diffs sans corps. **Fix** : consolidation multi-blocs.
2. `sanitize_diff` tronquait au 1er saut de ligne (contexte vides sans espace préfixe)
   → « no net change » au git-apply. **Fix** : ligne vide = ligne de contexte.
3. En régénération, le modèle aligne ses hunks sur la **version upstream mémorisée**
   du package (packages swe-smith célèbres), pas sur le mutant → mismatach systématique.
   **Fix** : fichier-complet uniquement + note anti-mémorisation dans le prompt.
4. **max_tokens=6000 × modèle à raisonnement long = silence du livrable** : 34/37
   réponses ont plafonné à 6000 avant même d'émettre le fichier — le raisonnement
   mange tout le budget. Toute fenêtre future avec ces familles doit prévoir
   max_tokens ≥ 16k et le logger.

**Ce qui tient** : le RCT scellé (négatif propre), l'instrument d'énergie latente
(0.817/0.735 mesurés LOAO), et la discipline elle-même — 5 amendements RCT + 2 ladder,
chaque fenêtre écartée conservée `discarded-window-*/`, chaque chaîne ancrée OTS.
**Ce qui manque pour la claim business** : une fenêtre de mesure absolue sur modèles
forts — en attente d'une nouvelle enveloppe owner. Protocole ladder scellé (chaîne
`63006531`) — rejouable tel quel.

---

## Addendum 2026-08-10e — prédiction sélective : le régime haute-confiance existe

Après le stop budgétaire, calcul local gratuit sur le pool (113 patchs / 69 tâches) :
l'instrument a-t-il un sous-ensemble où il ne se trompe JAMAIS ? Protocole LOAO-strict
(seuil médiane-train par fold, confiance = marge au seuil ; couverture décidée après
assignation hors-pli) — la question de Var-JEPA posée à nos données :

| couverture | n | acc GOLD (énergie, but connu) | IC95 Wilson |
|---|---|---|---|
| 100 % | 113 | 0.735 | [0.646, 0.807] |
| 75 % | 85 | 0.824 | [0.729, 0.890] |
| 50 % | 56 | 0.839 | [0.722, 0.913] |
| **25 %** | **28** | **1.000** | **[0.879, 1.000]** |
| 10 % | 11 | 1.000 | [0.741, 1.000] |

Lecture : (i) la courbe est **monotone croissante en sélectivité** — l'instrument SAIT
quand il sait ; (ii) à 25 % de couverture (décisions à marge > quartile), exactitude
parfaite avec borne basse Wilson 0.879 > majorité 0.611 — **premier point déployable
de l'instrument** : ne trancher que le quart confiant, s'abstenir sinon ; (iii) l'axe
goal-free F1 ne sélectionne pas (acc décroît avec la couverture) — la sélectivité est
une propriété de l'axe goal-conditionné, cohérent avec G1.

Conséquence design (reportée dans `docs/world-model-mcp-design.md`) : le MCP ne doit
pas PREDIRE partout — il doit prédire au quart hautement confiant et s'abstenir sinon
(Var-JEPA validé chez nous, gratuitement). Artefact : `data/landing/act2-pilot/s1-selective.json`.
Script : `scripts/act2/s1_selective_prediction.py`. Zéro call galere.

---

## Addendum 2026-08-10f — S3/S4/S5 : l'instrument amélioré à 0 call (confiance × combinaison × encodeur × n)

Trois chantiers locaux exécutés dans la foulée de S1 (scripts `s3_confidence_combination.py`,
`s4_encoder_swap.py`, `s5_pool_extension.py` ; artefacts `s3-confidence.json`,
`s4-encoder-swap.json`, `s5-extension.json` + `latent-pool-v5.*`). Contrôles positifs à
chaque étape : repro exacte S1 (0.735 / 1.000@25 %) et repro bit-stable uxc-base local
(AUC 0.817 CPU/MPS = node GPU).

### S3 — estimateurs de confiance & combinaison GOLD × F1 (n=113, LOAO-strict)

| méthode | AUC | acc100 | cov@≥0.95 (borne basse Wilson > maj) |
|---|---|---|---|
| GOLD + marge brute (S1) | 0.817 | 0.735 | 25 % |
| GOLD + Platt / + bootstrap | 0.795 | 0.69 | 25 % |
| GOLD + densité k-NN | 0.817 | 0.735 | **0 %** ✗ |
| GxF z-somme naïve (0 param appris) | **0.890** | 0.637 (seuil médiane mal placé) | 25 % |
| **GxF logreg λ=1 (Platt / bootstrap)** | 0.845 | **0.743** | **30 %** |

Deux leçons mesurées : (i) pour l'axe GOLD seul, **aucun estimateur ne bat la marge
brute** de S1 — la densité k-NN est franchement mauvaise, Platt/bootstrap parités ;
(ii) la **combinaison apprise gagne** : logreg 2D régularisée (λ=1.0) pousse la
couverture haute-fiabilité de 25 → **30 %** (0.971 [0.851,0.995] à n=34) avec acc100
équivalente (0.743 vs 0.735). Piège identifié : à λ=1e-3 la logreg 2D **sépare
complètement** sur les folds (poids biais −7.2, F1 +25 mesurés → AUC 0.706) — à n~100,
λ fort obligatoire. La z-somme naïve a le meilleur AUC (0.890) mais un seuil médiane
déplacé : à réserver au **ranking**, pas au verdict.

### S4 — swap d'encodeur gelé : uniXCoder-base reste champion (négatif propre)

| encodeur (gelé, 512 tok) | pooling | AUC GOLD | acc LOAO | cov@≥0.95 |
|---|---|---|---|---|
| **microsoft/unixcoder-base** (contrôle) | CLS | **0.817** | **0.735** | **25 %** |
| jinaai/jina-embeddings-v2-base-code 161M | mean | 0.810 | 0.726 | 10 % |
| Salesforce/codet5p-110m-embedding | (pooled) | 0.762 | 0.708 | 10 % |
| microsoft/codebert-base | CLS | 0.739 | 0.664 | 10 % |

Le choix uxc-base n'était **pas arbitraire** : 3 challengers de 3 familles (BERT-code,
T5, RoBERTa) tous sous le contrôle, et leur **région haute-confiance** (le produit réel)
est dégradée (10 % vs 25 %). Reste ouverte l'hypothèse « beaucoup plus gros »
(gte-Qwen2-1.5B-instruct et au-delà) — future work, coût non justifié après 0/3 à cette
échelle. Note d'ingénierie : les remote codes jina/codet5p exigent transformers 4.49
(incompatibles 5.x) — `.venv-embed` dédié créé, git-ignoré.

### S5 — pool étendu 113 → 131 à 0 call (récupération rct-v1)

Audit des gisements 0-call : fenêtres pilotes sans raw replies persistées → 281 slots
non-applicables **irrécupérables** ; discarded-window-1..3 = raw replies sans exécution
conservée → labels impossibles (node docker down) ; e1-boltzmann = 128 candidats mais
mapping candidat→verdict non persisté → écarté honnêtement. **rct-v1/results (série
scellée) : 18 patchs appliqués ajoutés après dédup (task, sha256)** (4 positifs,
mixture b0/b1 déclarée) → n=131, 48 positifs, 74 tâches.

| instrument | AUC | acc100 | cov@≥0.95 | en absolu |
|---|---|---|---|---|
| GOLD+marge (113) | 0.817 | 0.735 | 25 % | 28 patchs à 1.000 [0.879,1.000] |
| GOLD+marge (131) | **0.830** | **0.771** | 25 % | **33 patchs à 1.000 [0.896,1.000]** |
| GxF+platt (131) | **0.864** | 0.725 | **30 %** | **39 patchs à 0.974 [0.868,0.995]** |

Le n supplémentaire resserre les bornes et monte le GOLD à 0.771@100 % (majorité 0.634) ;
le combiné confirme son avantage de queue (0.974 @ 30 % — meilleur point déployable du
projet). **Verdict campagne** : l'amélioration venue de la méthode (λ, combinaison) est
réelle mais plafonne ; la marge restante est dans n (doctrine confirmée : 200+ patchs) et
dans la persistance systématique des raw replies dès le premier appel — leçon appliquée
au RCT, trop tard pour les fenêtres pilotes.

---

## Addendum 2026-08-10g — S6/S6b/S7 : +32 patchs à 0 call, et un poison mesuré

Le gisement boltzmann-e1 (128 candidats T=0.7 × 32 tâches frozen32, générés 08-09) n'avait
jamais été exécuté. Runner node (`s6_boltzmann_label_exec.py`, même protocole docker que
le pilot : bug gold → patch → py_compile → F2P → P2P), 128 exécutions en ~5 min,
0 call galere :

| passe | applicables | F2P verts (P2P verts inclus) |
|---|---|---|
| S6 apply strict | 14/128 | 4 |
| S6b récupération sanitize→recount→ré-export (procédure canonique) | 18/92 | 9 |
| **total** | **32/128 (25 %)** | **13** |

**Découverte auditing E1 (correction au NON du 08-09c)** : E1 avait mesuré 1/32 theory
et 1/32 random — mais les 4 candidats gagnants réels étaient exceptiongroup-c1,
getmoto-c3, icecream-c2, sqlglot-c1. Ni theory ni random ne trouvaient la majorité des
gagnants *présents* dans le 4-plet : le verdict « l'énergie ne départage pas au choix
ponctuel » tient, renforcé.

**Le poison, mesuré nommément** : ajout des 32 au pool (163) → GOLD 0.830→0.790, queue
haute-confiance effondrée (cov@≥0.95 → 0 %). Stratification par sous-ensemble :

| sous-ensemble | n | AUC | acc100 |
|---|---|---|---|
| v5 (pilot+rct) | 131 | 0.830 | 0.771 |
| boltzmann stricts seuls | 14 | 0.750 | dans la distribution |
| **boltzmann recovered seuls** | 18 | **0.543** | **hasard pur** |

Les diffs réparés mécaniquement (comptes de hunks ré-écrits, verbiage coupé) ne sont plus
le texte que le modèle a écrit — leur géométrie latente est décorrélée du couple (état,
but). **Pool final v6 = v5 + 14 stricts = 145** (52 positifs, 78 tâches, recovered exclus,
conservés marqués `recovered=true` pour traçabilité) : GOLD AUC 0.822, acc100 0.779,
**29 patchs à 0.966 [0.828,0.994] @20 %** — équivalent v5 dans tous les IC, n supérieur.

**Trois leçons écrites au doctrinal** : (i) la composition du pool est un facteur de
première classe — n brut ne suffit pas, la fidélité textuelle du diff non plus ne
pardonnera pas (recovered = poison) ; (ii) leçon **produit** pour le MCP : il faut scorer
le candidat dans la forme où le modèle l'a écrit, *avant* toute réparation mécanique ;
(iii) pour atteindre 200+ il faudra de la génération nouvelle (raw replies persistées dès
le 1er appel) — la récupération a été faite, elle est épuisée.
Artefacts : `boltzmann-e1/labels/` (128, sur node + rapatriés), `latent-pool-v6.*`,
`s7-boltzmann-extension.json`. Scripts : `s6_boltzmann_label_exec.py`,
`s6b_boltzmann_recover_exec.py`, `s7_pool_boltzmann.py`.

---

## Addendum 2026-08-10h — S8 : encoder-swap vers un LLM-instruct gelé (Qwen2.5-Coder-7B) — premier gain mesuré de queue

**Contexte** : le gate v2 « CWM » est tué par la licence (visée commerciale). Test
intermédiaire à 0 call : un LLM de code généraliste gelé comme encodeur (last-token
pooling, 512 tok, fp16 sur wmel-gpu RTX-5000 — Turing sans bf16, fp16 natif).
Protocole identique à S4/S7 (pool v6, n=145, LOAO strict). Contrôle positif :
uxc reproduit sur v6 (0.822/0.779) à l'identique.

| instrument | AUC | acc100 | cov@≥0.95 | queue |
|---|---|---|---|---|
| uxc GOLD+marge (S7) | 0.822 | 0.779 | 20 % | 29 à 0.966 [0.828,0.994] |
| uxc GxF λ=1 (S7) | 0.828 | 0.710 | 20 % | idem |
| Qwen-7B GOLD seul (marge) | 0.815 | 0.710 | **25 %** | **36 à 1.000 [0.904,1.000]** |
| **Qwen-GOLD × uxc-F1 (croisé)** | **0.852** | 0.724 | **25-30 %** | 36 à 1.000 @25 % + **0.903 @50 %** |

(Note pooling : `mean` légèrement sous `last` sur Qwen — 0.802/0.731 — retenu `last`.)

**Lecture honnête** : en AUC, les trois instruments sont **statistiquement à égalité**
(IC se recouvrent ; le croisé 0.852 n'est pas séparé de 0.828). Le gain est sur la
**métrique produit** : la queue haute-confiance passe de 29 patchs à 0.966 à
**36 patchs à 1.000, borne basse Wilson 0.904**, et le croisé tient 0.903 à 50 %
de couverture (vs 0.833 pour uxc).

**Verdict sous la règle pré-déclarée ce matin (AUC GOLD > 0.864 ET cov@≥0.95 > 30 %) :
le croisé (0.852, 30 %) NE LA PASSE PAS — il est enregistré comme CANDIDAT v2, non
promu, réévaluable tel quel à la prochaine promotion du pool (n↑, même règle).**
Rectificatif d'honnêteté : une première rédaction de cet addendum disait « promu »
en relisant le gate plus doux d'hier — le gate est celui déclaré AVANT le run ;
on ne bouge pas les poteaux après mesure. Production : latent-gate reste sur v1.

**Contamination (déclarée)** : les repos swe-smith sont publics — même clause
qu'uniXCoder (code statique vu au pretraining, labels = mutants récents non publiés).

---

## Addendum 2026-08-10i — S9 smoke : LoRA causal-LLM vs énergie gelée — NÉGATIF net

**Protocole** : Qwen2.5-Coder-0.5B + LoRA r8 (q,v), verdict-token {PASS, FAIL} supervisé
(CE 2-classes), 2 epochs, LOAO complet 69/69 folds sur le pool 113 — co-honoré avec la
baseline uxc recalculée sur les mêmes folds. Wmel-gpu, fp16 natif (Turing).

| instrument | acc100 | IC95 | @25 % |
|---|---|---|---|
| uxc-énergie gelé (champion) | **0.735** | [0.646, 0.807] | **1.000** [0.879, 1.000] |
| LoRA 0.5B | 0.602 | [0.510, 0.687] | 0.607 — **sous la majorité** (0.611) |

**Verdict** : à n=113, le fine-tune n'atteint même pas la baseline majoritaire.
Convergence E2 (fine-tune détruit) + S9 (fine-tune n'apprend pas) : **à ce régime de n,
toute capacité entraînée sur nos patchs est perdante face au gelé + géométrie.**
Le vrai run 7B/32B (S9') garde son sens uniquement avec n beaucoup plus grand ou une
supervision traces NLEX à l'échelle — ni l'un ni l'autre ne tient dans le budget restant.
Artefact : `data/landing/act2-pilot/s9-smoke.json` + copie Mac. Script :
`scripts/act2/s9_lora_smoke.py`.

---

## Addendum 2026-08-10j — S10 SCAMPER + ERRATUM sur 08-07c : le signal est dans diff↔gold, pas dans l'état

**Erratum d'abord (protocole `governance/erratum-protocol.md`, direction négative).**
L'addendum 08-07c publiait « diff↔gold seul : AUC 0,174 — pas de corrélation naïve
u→û ». **Ce chiffre est faux** : recalcul direct de cos(E_diff, E_goal) sur les deux
pools donne **AUC 0.826 (n=113) et 0.828 (n=145)**. Le bug (signe/orientation dans
`latent_energy_eval.py`) est corrigé en S10. Invalidés en conséquence (marqués
superseded, pas réécrits) : la phrase « ce n'est pas la distance "ses diff à gold"
qui porte le signal mais l'espace conjoint » et la conclusion de cohérence avec IWM
fondée dessus. Les nombres état-seul (0.543), énergie conjointe (0.817), buts permutés
(0.567) sont eux inchangés et re-mesurés lors du contrôle positif.

**S10 — balayage SCAMPER des variantes du modèle (LOAO strict, numpy seul, 0 call).**
Contrôle positif : repro exacte de S7 (0.822/0.779 ✓). Pool v6 (n=145) :

| variante | AUC | acc100 | cov@≥0.95 |
|---|---|---|---|
| champion uxc GOLD (état∘diff vs état∘gold) | 0.822 | 0.779 | 20 % |
| **E1 diff→gold SEUL (cos direct)** | **0.828** | **0.779** | 20 % |
| E2 état→gold seul (sans diff) | 0.446 | 0.448 | 0 % ✗ bruit |
| M1 all-but-the-top k=1/3 | 0.812/0.823 | 0.752 | 20 % (n.s.) |
| M1 k=8 | 0.828 | 0.710 | 10 % (dégrade) |
| **C1 GxF 4 espaces (uxc+Qwen, λ=2)** | **0.856** | 0.717 | **30 %** |
| R1 temporel : train {frozen32,rct,boltzmann} → test extension-128 | AUC 0.763 | acc 0.600 [0.497,0.695] | — |

**Lecture doctrine — trois faits qui déplacent le modèle mental :**
1. **L'état n'apporte RIEN** : diff↔gold seul = le champion (0.828 vs 0.822, égalité
   IC). Élimination honnête : le modèle peut être simplifié à 2 embeddings (diff, but)
   — moins cher, même pouvoir. L'état seul = bruit (0.446 < hasard : sous-ensemble
   interestingly anti-informatif — à creuser plus tard si utile).
2. **La combinaison multi-espaces (uxc + Qwen) tient** : AUC 0.856 — meilleur AUC
   mesuré du projet ; cov 30 %. Sous le gate pré-déclaré v2 (AUC > 0.864 ET cov > 30 %)
   : **NE PASSE PAS** — enregistré sans promotion (les poteaux ne bougent pas).
3. **R1 temporel** : la généralisation à la fenêtre postérieure (extension-128, tirée
   après) est affaiblie mais réelle (AUC 0.763 vs 0.822 LOAO) — le modèle transfère
   à la dérive de distribution, partiellement. Utile pour la lecture externe.

Artefact : `data/landing/act2-pilot/s10-scamper.json`. Script :
`scripts/act2/s10_scamper.py`. La bascule « modèle simplifié diff↔gold » pour
latent-gate v2-candidat est sur la table, évaluée à la prochaine promotion du pool.

**Artefacts** : `latent-pool-Qwen2.5-Coder-7B-Instruct-{last,mean}.npz` (GPU node,
fp16) + `s8-qwen7b.json`. Script : `scripts/act2/s8_cwm_probe.py` (fp16 forcé sous
Turing). Note ops : le node WMEL-gpu-strong est resté down ~3 h (20:14→23:10) après
arrêt manuel du vLLM OpenResearcher — repris via KVM owner ; probe tourné sur
wmel-gpu (RTX 5000).

---

## Addendum 2026-08-11/14 — S11 : le « POISON » du 11 était une corruption de join ; les données externes saines sont POISON quand même (OOD mesuré, wmel-gpu)

**S11 (run initial 2026-08-11, node wmel-gpu)** : extension du pool par les
trajectoires EXTERNES HF `SWE-bench/SWE-smith-trajectories` (8 shards, 25 826 traj
claude-3.7/3.5/gpt-4o, labels `resolved` du harness officiel). Verdict initial :
contrôle v6 OK, **ext seul AUC 0.495 → POISON déclaré**. Ce verdict était
**contaminé par un bug amont** :

**La corruption (mesurée nommément le 14)** : la colonne `patch` de l'export HF est
DÉSALIGNÉE de sa colonne `instance_id` (15 910 diffs sur 16 052 dans un autre repo
que leur tâche ; ex. tâche boltons → diff dask). L'AUC 0.495 du 11 mesurait le
désalignement, pas les patchs externes. Fichiers du run v0 renommés
`*.v0-corrupt-patchcol.*` et conservés (Mac + node), aucun chiffre v0 publié.

**Le fix (2026-08-14, 0 call)** : le diff final de l'agent est reconstruit depuis la
colonne `messages` (trajectoire SWE-agent : dernier bloc `<diff>…</diff>` de
l'observation de submit — texte TEL QU'ÉCRIT, règle S6). Validation : 97 % des diffs
extraits partagent ≥1 fichier avec le gold sur sonde ; audit join final :
**98,5 % des résolus partagent ≥1 fichier gold** (6 784/6 887) — les labels sont
alignés. Join corrigé : **15 170 lignes** (8 396 sans diff de submit, 2 147 dédup),
**11 094 tâches nouvelles**, positifs 45,4 %. Embed uxc-base sur node (RTX 5000).

**Résultats (LOAO-strict, critères pré-enregistrés du 11 inchangés)** :

| mesure | valeur | lecture |
|---|---|---|
| contrôle v6 GOLD | AUC 0.822 / acc 0.779 | repro exacte ✓ |
| **ext seul GOLD** | **AUC 0.576** / acc 0.556 | **< 0.65 → POISON confirmé** |
| diff↔gold seul (recette S10) | 0.579 | égal à l'énergie conjointe |
| F1 attracteur goal-free (recette G1) | 0.333 | **inversé**, pas neutre |

**Stratification (aucun sous-ensemble ne sauve le signal)** : partage-fichier-gold
0.568 (n=14 602) vs non-partage 0.561 (n=568) ; diff court 0.551 vs long 0.548 ;
claude-3.7 0.576 vs claude-3.5 0.555 ; mono-fichier quasi absent (8 lignes — ces
trajectoires embarquent systématiquement les fichiers scratch de l'agent) ;
rang-moyen GOLD+F1 = 0.437 (la combinaison qui gagnait +0.021 sur le pool v6
s'inverse elle aussi sur l'externe).

**Lecture doctrine** : ce n'est plus une corruption, c'est un fait de distribution —
l'instrument v6 (patchs galere mono-hunk) est **lié à sa distribution d'auteur et de
géométrie de diff** ; les trajectoires externes multi-fichiers habitent une région
latente où ni l'énergie-but ni l'attracteur d'échecs ne transfèrent (l'axe F1
s'inverse : les succès externes sont *loin* de l'amas d'échecs v6). Leçon produit
ajoutée à la leçon S6 (08-10g) : **le modèle-auteur du pool est un facteur de
première classe, au même titre que la fidélité textuelle** — un pool « mélangé » ne
s'improvise pas, il se mesure d'abord.

**Verdict final S11** : pool canonique **v6 inchangé (145)** ; la gate v2
(AUC > 0.864 ET cov > 30 %) n'est approchée ni par v7 (= v6+v0-corrupt, jamais
construit), ni par aucun sous-ensemble externe déclaré ici. Les 15 170 lignes
restent archivées sur le node (artefact `s11-ext-pool.npz`) pour toute étude future
sur l'OOD — pas pour le gate.

**Nota protocole (GxF)** : le recalcul 2026-08-14 sur v6 a révélé que la feature F1
côté TRAIN de `gxf_loao` incluait les voisines de même tâche (+ la diagonale) —
fuite douce, non conforme au LOAO-strict déclaré. Version corrigée (exclusion tâche
partout) : v6 GxF **AUC 0.858 / acc100 0.786 / cov 30 %** vs 0.828/0.710/20 %
laxiste — le strict est meilleur. Les chiffres GxF des addenda S3/S5/S7/S10 sont
ceux de la variante laxiste ; GOLD (contrôle de tous les runs) est inchangé.

**Zéro call galere sur toute la session S11.** Artefacts Mac :
`data/landing/act2-pilot/s11-pool-v7.json`, `s11-diag.json`, `s11-diag.v1b.log`,
`s11-eval.v1.log`, `s11-embed.v1.log`, `*.v0-corrupt-patchcol.*`. Node :
embeddings 15 170×3 (`s11-ext-pool.npz`). Scripts : `scripts/act2/s11_ext_pool.py` (join corrigé,
extraction `messages`, gxf strict, AUC par rangs), `scripts/act2/s11_diag.py`.

---

## Addendum 2026-08-14b — S12 : la fenêtre de génération complétée, pool v7 (v6 + 32), et première AUC au-dessus de la barre gate v2

**Complétion S12-G/S12-L.** La génération a été arrêtée au cap pré-enregistré
(251 calls / cap 250, entrée budget du 14), à 144/156 slots complétés — 4 slots
interrompus en vol (3 sans raw : l'appel n'a jamais terminé ; 1 avec raw,
`ea842rxy-d1` : extraction seule a posteriori, diff unappliable → `no-diff`,
0 nouvel appel), 8 jamais démarrés. La labellisation docker (wmel-gpu) a crashé
sur les 3 orphelins sans `meta.json` ; garde ajoutée dans `s12_label_exec.py`
(meta manquante → erreur enregistrée, plus d'arrêt du run). Bilan S12-L des
148 slots : **83 no-diff, 7 non-compilables, 62 appliqués — 23 f2p vert, 0 p2p
régressé**. Tally final : `s12-label.log` (`== S12-L : 145 déjà mesurés, 4 exécutés ==`).

**Construction du pool (stage `pool` de `s12_pool.py`, 0 call).** Règle de
promotion : appliqué ∧ compile ; `y=1` ssi f2p ∧ (p2p ok ou non déclaré) ;
dédup sha256(diff) contre v6 ; state/gold repris de la ligne v6 de la même
tâche. Sur les 62 appliqués : **23 dédupliqués — dont 16 des 23 verts sont
byte-identiques à des diffs v6 existants** (le modèle redécouvre les mêmes
corrections, signal de convergence, pas de nouveauté), 7 écartés car ils ne
compilent pas, **32 promus (7 positifs, 25 négatifs applicables-mais-faux)**.
**Pool v7 = 145 + 32 = 177 lignes, 59 positifs, 78 tâches.** (Le nom `v7` est
réutilisé : le fichier `s11-pool-v7.json` est un verdict POISON, pas un pool.
L'objectif pré-enregistré « 200+ patchs labelisés » n'est pas atteint — 177 ;
la dédup contre v6 et les 12 slots jamais complétés expliquent l'écart.)

**Évaluation (stage `eval`, LOAO-strict inchangé, numpy seul, 0 call ;
embeddings uxc des 32 nouvelles lignes sur node, concat bit-identique aux 145
v6 — contrôle positif : repro exacte 0.8215/0.7793 ✓ attendus 0.822/0.779).**

| instrument | v6 (n=145) | **v7 (n=177)** | lecture |
|---|---|---|---|
| GOLD uxc (contrôle) | 0.822 / 0.779 / cov 20 % | 0.824 / 0.774 / **cov 25 %** | AUC plate (IC recouvrent), couverture +5 pts |
| **GxF strict** | 0.858 / 0.786 / cov 30 % | **0.867 / 0.797 / cov 30 %** | **première AUC > 0.864 mesurée du projet** ; à cov 30 % fixe, acc 0.962 [0.872,0.990] (n=53) ; cov 10 % : 18/18 |

**Queue haute-confiance (top 25 %, n=44, GxF strict)** : 35 lignes v6
(acc 0.943) + **9 lignes s12, toutes bien classées (9/9)** — l'assort généré
n'a pas dilué la queue, il l'a épaissie avec des lignes correctes.

**Verdict gate v2 pré-déclarée (AUC > 0.864 ET cov@≥0.95 > 30 %)** : GxF strict
v7 passe la barre AUC (0.867) mais cov = 30 % pile, pas strictement supérieure
→ **NE PASSE PAS, tel que déclaré.** Les poteaux ne bougent pas : v7 est
enregistré comme CANDIDAT, pool canonique reste v6 tant que l'owner n'a pas
décidé. C'est la première fois qu'un instrument touche la barre AUC ; il manque
de la couverture, donc du label — exactement ce que la fenêtre S12 visait.

**Limites déclarées** : (i) les 32 lignes viennent de 78 tâches déjà présentes
dans v6 — le LOAO reste propre (tâche entière hors fold) mais la nouveauté est
« nouveaux diffs sur tâches connues », pas « nouvelles tâches » ; (ii) 16 verts
déduplés byte-identiques = le taux de nouveauté utile de la fenêtre est plus
bas que son taux de succès brut (23) ne le suggère ; (iii) le variant C1
4-espaces (uxc+Qwen) et R1 temporel n'ont pas été re-mesurés sur v7 (embeddings
Qwen non recalculés pour les 32 lignes — à faire avant toute décision de
promotion si la combinaison multi-espaces reste l'instrument visé).

**Zéro call galere sur toute la construction/évaluation v7.** Artefacts :
`latent-pool-v7.json/.npz` (177×3×768), `s12-new-embed.npz`,
`s12-pool-build.json`, `s12-pool-v7-eval.json`, `s12-label.log`. Scripts :
`s12_gen.py`, `s12_label_exec.py` (garde meta), `s12_pool.py`
(stages pool/embed/eval).

---

## Addendum 2026-08-15 — nuit autonome S13/S14 : le juge LLM, le bug d'extraction, le pool v8 (n=207), et l'ensemble 0-paramètre qui passe la gate v2

**Nuit 2026-08-14→15, accord owner (« 8 h en totale autonomie, itérer jusqu'à un
score de qualité »).** Pré-enregistrement : fenêtre S13 juge (cap 250) + fenêtre
S14 gen (cap 350 puis W-S15 conditionnelle cap 250 ; enveloppe ≤ 600 hors S13).

**S13 — juge Qwen3.8-2.4T-A95B-NVFP4 zero-shot (nuit, 00:08).** 177 lignes v7,
T=0, entrée = state+diff (jamais le gold), sortie {"probability": 0-100}.
Finding protocole d'abord : le thinking du 2.4T n'est pas débrayable sur ce
backend (« Disabling thinking is not supported ») et saturait 4 000 puis
16 000 tokens de raisonnement sans produire le content (mesuré row 0,
finish_reason=length, raisonnement convergent mais coupé) → max_tokens 32 000,
amendement loggé avant tout run complet (~8 calls de calibration).
**Juge : AUC 0.818 | cov@≥0.95 30 % | acc@30 % 0.981 [0.901,0.997] | 18/18 @10 %**
— jeu égal avec GOLD uxc (0.824) *sans voir le gold*, la condition de production.
Pairing vs GxF strict : erreurs complémentaires (97 accord correct, 44 GxF seul,
24 juge seul, 12 les deux faux). 229 calls fenêtre S13 (cap 250), 1 ligne v8
sans score (row 187, parse ×2 échoué — non reprise, déclarée).

**S14-G (nuit, 03:38) — génération sur 60 tâches HORS v6 × 2 tirages =
120 slots, auteur identique S12, 235 calls.** Fait marquant : **112/120 no-diff**,
contre 56 % en S12. Diagnostic au matin : les raws contiennent des diffs valides
tronqués par **un bug de `sanitize_diff`** — une ligne de contexte vide du modèle
(`" "` → `""` après rstrip) déclenchait le `break` en plein hunk. Victimes
mesurées : 42 des 83 no-diff S12 + 47 des 112 no-diff S14. Bug ancien (jamais
exposé en S12 où les petits hunks de mutants évitaient les lignes vides ;
le panel S14 à hunks longs l'a révélé). **Correctif** (`pilot_run.py`,
amendement documenté dans la fonction) : ligne vide dedans d'un hunk déjà
ouvert reprise comme contexte. Prompt/panel/harness inchangés sinon.

**Ré-extraction (matin, 0 call)** : `s14_reextract.py` rejoue la chaîne
d'extraction corrigée sur les raws persistées des no-diff S12+S14 :
**29 slots récupérés** (15 S12 + 14 S14 ; les ~106 restants deviennent
« unappliable » explicites — le modèle n'avait pas produit de diff applicable,
cette fois pour de vrai). Labellisation docker : S14-L 120 slots
(21/22 appliqués, **9 verts**, 0 p2p régressé), S12-récupérés 15 slots
(15/15 appliqués, **8 verts**).

**Pool v8 = v7 + 30 lignes nettes = 207 (73 positifs, 94 tâches).**
19 lignes S14 + 11 lignes S12-récupérées ; 6 autres S12-récupérées dédupliquées
byte-identiques à v7. Objectif pré-enregistré « 200+ patchs labelisés » atteint.
Embeddings uxc node (concat bit-identique, contrôle v6 0.822/0.779 repro ✓) +
Qwen2.5-Coder-7B-last (207×3, recette S8).

**Mesures v8 (LOAO-strict)** :

| instrument | AUC | acc100 | cov@≥0.95 | lecture |
|---|---|---|---|---|
| GOLD uxc | 0.825 | 0.763 | 25 % | +0.001 vs v7, cov stable |
| GxF strict uxc | 0.855 | 0.787 | **0 %** | recule vs v7 (0.867/30 %) |
| C1 GxF 4 espaces (uxc+Qwen, λ=2) | 0.843 | 0.720 | 10 % | recule vs v6 (0.856) |
| GBDT v3 features (refit) | dégénéré tout-positif | 0.377 | — | l'instrument features ne scale pas |

**Lecture honnête de la régression GxF** : restreint aux 177 lignes v7, GxF
dans la géométrie v8 monte à **AUC 0.870** (> 0.867) — les lignes nouvelles
servent d'ancres aux anciennes. Les 30 nouvelles lignes, elles, ne font que
**0.750** : familles de tâches/mutations inédites (lm_rewrite, combine, 16
nouvelles tâches), la géométrie apprise n'y est pas encore fiable, et leurs
erreurs confiantes cassent la couverture. Le signal global progresse, la queue
sélective se dilue — le coût prévu de l'extension de domaine.

**L'ensemble 0-paramètre (proposition après observation de la complémentarité
S13 — déclaré ici, pas pré-enregistré)** : moyenne arithmétique des probabilités
`0.5×GxF + 0.5×juge`, zéro paramètre appris (esprit « z-somme naïve » S3).

| ensemble (v8, 206 lignes) | AUC | cov@≥0.95 | acc@30 % |
|---|---|---|---|
| GxF seul | 0.854 | 0 % | 0.935 |
| juge seul | 0.830 | 30 % | 0.984 |
| **moy-probas** | **0.891** | **50 %** | **1.000 [0.942,1.000]** (n=62) |
| moy-rangs (descriptive) | 0.906 | 20 % | 0.919 |

**Test d'honnêteté sur v7 (toutes lignes déjà jugées à 00:08, avant toute
donnée S14)** : l'ensemble y passait déjà — **AUC 0.893 / cov 50 % /
acc@30 % 1.000 [0.932,1.000]**. La passe n'est donc pas un artefact du lot
de nuit ; mais l'instrument a été construit après avoir vu le pairing, et le
critère « passé sur v7 » est post-hoc — le statut est **CANDIDAT v3**, pas
promu. Pour une validation prospective : geler le combinateur (identique,
0 paramètre) et le mesurer sur des lignes JAMAIS vues (prochaine fenêtre de
génération W-S15, tirages d3-d4 sur les 60 tâches S14, pré-enregistrée cap
250, non consommée).

**Verdict gate v2 (pré-déclarée 2026-08-10, poteaux inchangés)** : l'ensemble
moy-probas satisfait les deux critères sur v7 et v8 ; GOLD et GxF seuls non.
Promotion = décision owner, sur validation prospective recommandée.

**Budget consommé** : S13 juge 229 calls (+ ~8 calibration), W-GEN-S14 235
calls. Aucune dépense hors fenêtres déclarées. W-S15 non entamée (arrêt de
l'autonomie au retour owner ; la dépense suivante est sa décision).

**Incident supervision (nuit)** : le run autonome a généré les 120 slots
correctement mais s'est arrêté à 03:39 sans labelliser — rsync vers le node
échoué (répertoire cible jamais créé, rsync sans `--mkpath`) et le script de
gen est mort sur `UnboundLocalError` (variable `mode` non initialisée quand les
2 appels d'un slot échouent — corrigé). Le superviseur et `s14_gen.py` sont
patchés (mkdir avant rsync, retry de phase, marqueur de reprise). Rien n'a été
perdu : les 120 slots étaient complets sur disque au matin.

**Artefacts** : `latent-pool-v8.json/.npz` (207), `latent-pool-v8-qwen7b-last.npz`,
`s14-pool-build.json`, `s14-pool-v8-eval.json`, `s14-extras.json`,
`reextract-report.json`, `s13-judge.json` + `s13-judge/` (raws probas 206/207),
`s14-label-c1.log`, `s12-label-reextract.log`, `autonomy-8h/journal.md`.
Scripts : `s13_llm_judge.py`, `s13_judge_extend.py`, `s14_gen.py`,
`s14_reextract.py`, `s14_pool.py`, `s14_qwen_embed.py`, `s14_extras.py`,
`autonomy_8h.sh` (patché), `pilot_run.py::sanitize_diff` (correctif),
`s12_label_exec.py` (garde meta + stage paramétrable).
