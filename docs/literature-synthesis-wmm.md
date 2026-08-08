# Synthèse littérature World-model / JEPA → application Latent-Imagination (2026-08-07)

Corpus : 72 papiers du dossier `~/Documents/Dossier personnel/World-model-litterature` (source awesome-jepa).
Lecture ciblée sur : **prédire le succès d'un fix logiciel (tests passent) depuis (état, diff), À 100-500 exemples** — notre régime Act II.

Ce qui suit est mesuré dans les papiers. Tout le reste est supposition éliminée ici.

---

## 1. Highlights par papier (les 9 piliers pour nous)

| # | Papier | Thèse | Formule/expérience clé | Ce qu'il nous dit, Noir sur blanc |
|---|---|---|---|---|
| H1 | **LeCun 2022** (§3, p.7) | WM = simulateur en latent, jamais pixel | `E(x,y,z) = D(s_y, Pred(s_x,z))`, z = ce qui n'est pas prédictible depuis x (§4.2 p.19) | Le « scorer de flip » doit être une **énergie dans l'espace latent**, pas f(diffs tokens) |
| H2 | **I-JEPA 23** | Target-representation ≫ target-pixel | Linear-probe 0.669 vs 0.407 (Table 7 p.8) | Le patch brut est bruité : encoder avant de scorer, toujours par embedding d'un encoder |
| H3 | **IWM 24** (Garrido) | Équivariant vs invariant : sans conditionner sur l'action, on collapse sur invariance | Table 1 p.5 : no-cond → MRR 0.00 | **Le diff EST l'entrée du prédicteur** ; pas un latent résiduel |
| H4 | **Destrade 26** | La métrique latente doit approximer −valeur goal-conditionnée | `Vθ(s,g) = −‖E(s) − E(g)‖₂` (Eq.1 p.2), expectile | Apprendre « la distance latente ≈ travail avant tests verts » |
| H5 | **EB-JEPA 26** (Terver) | recette 1-GPU : `L = L_pred(rollouts) + VICReg + L_sim + L_IDM` | Table 4 p.8 : sans IDM → 1% (de 97%) (collapse par corrélations de surface) | **L'IDM (prédire le diff depuis couple (latent, latent′)) est le testeur anti-collapse le moins cher ; le plus efficace** |
| H6 | **Toso 26** | Le latent hérite des "slow features" (fond/distracteurs) ; fixer par bisimulation | PointMaze shifts : 0.78–0.86 homogène vs DINO-WM 0.48 → 0.80 | **Notre boilerplate/repo/commentaire = leur "fond" : PCA-VICReg de queue + mutations syntaxiques-font paires bisimilaires** |
| H7 | **LeJEPA 25** (Balestriero-LeCun) | Gaussienne isotrope = optimal pire-cas pour probing ; SIGReg | Lemma 1-3, Thm.1 p.5-6 ; coefficient spearman 99 % train-loss ↔ accuracy (α≈0.4) | À n=111 : **full-batch SIGReg, sélection de modèle sans labels** (LI mesure) |
| H8 | **Var-JEPA 26** (Gögl) | ELBO révèle : prédicteur JEPA == prior conditionnel, z gaussien absorbe l'inexpliqué | Table 2 p.8 : sélection 50 % les plus confiants → +7 points de accuracy | **Mesurer, puis s'abstenir** : le covariance-postérieur est plus fiable qu'un seuil de verdict |
| H9 | **Yu 25** | L'auxiliaire décide ce qui peut fusionner, pas la dynamique seule | Thm.1 p.3 : binary-aux + dynamique → 9 classes non-fusibles | Notre `P(tests-pass)` binaire est **trop pauvre** : enrichir (count, identity of failing tests) pour casser des bisimulations parasites |

## 2. Les ponts inter-papiers (le "où deux piliers se rencontrent")

| Pont | Ce qui relie | Ce qu'on peût faire |
|---|---|---|
| **IWM × Toso** | Conditionner = éviter l'invariance ; bisimulation = éviter les distractors | Diff entre en predictuer ; boilerplate muté donne paires bisimilaires — les DEUX dans le même régime | 
| **Yu × EB-JEPA** | L'auxiliaire dense = IDM | L'IDM de EB-JEPA EST l'auxiliaire le plus dense possible (prédire l'action) — Yu fournit la preuve manquante de EB-JEPA Table 4 |
| **LeJEPA × Littwin** | Forcer une distribution isotrope ≠ éliminer le bruit insuffisamment prédictif | Feature selection (Littwin ρ-filter) + SIGReg final (LeJEPA) : celles qui restent après filtrage ρ sont celles qu'on gaussianify |
| **Destrade × Toso** | Métrique −valeur ↔ invariance bisimulation | Les deux buts identiques : mergeable dans un seul objectif ; aucun papier n'a confirmé/rejeté empiriquement cette équivalence |
| **LeCun z-discret × Var-JEPA z-gaussien** | LeCun §4.2 veut z **discret** ; Var-JEPA utilise **gaussien** — contradiction actuelle de la littérature | Première surface de « déni contradictoire » à tester (discuter ci-dessous) |

## 3. Aller « ailleurs » — 6 pistes exploratoires inédites identifiées

Celles requièrent toutes peu de dépense supplémentaire à notre pool déjà créé — chaque test est juste du calcul local, aucun coût galere.

| # | Idée | Liés | Pourquoi original | Ce qu'on mesure |
|---|---|---|---|---|
| E1 | **Mutation-syntax paires** comme supervison bisimulation | Toso | Personne n'est allé bidirectionnel code ↔ sémantique invariance avec mutations légales (renommage d'idents, permute imports) | LOTO-acc après λ·L_bisim(mutations) vs sans |
| E2 | **Latent Bernoulli du verdict** (contre z-gaussien) | LeCun §4.2 / Var-JEPA | LeCun préconise z discret, tous les papiers modernes font gaussien — délai de contredit non résolu | Avec z discret vs gaussien : LOTO-acc inv |
| E3 | **Macro-action hiérarchique"** = chunk logique de diff | Zhang 26 | On applique HWM à des diffs multi-étapes : le bottom est 1 commit, le top = "intention" dim ≤ 5 | accuracy de planning du fix intégral |
| E4 | **World Model of Software** — premier papier | tous | Aucun texte JEPA entrainé **sur code** avec tests-exécutables comme signal de vérité — pas d'autre modalité a tests instantanés comme label | récipie complète ; pire, artefact |
| E5 | **IQL-metric ≈ bisim-metric ?** (tester l'équivalence) | Destrade × Toso | Rapprocher les deux papier, mesurer si la metric appris par expectile contient assez pour prédire la bisim | corrélation entre d(s,g) ≈ -v et d(s,g) sous bisim sur nôtres patches |
| E6 | **Auxiliaire multi-graine** (nb fails, identité test, durée) vs binaire | Yu | Thm 1 autorise enrichissement expérimental — preuve calculée mais non prouvée sur données realísticas | LOTO (précision binaires vs enrichis) |

**Ces pistes = le graph de la shareable "ailleurs"** — données déjà collectées (111 patches / 71 tasks), invariants mesurables sans dépasser le budget actuel (247 galere calls restants sont intacts).

## 4. Limites honnêtes (quatre paris supportés, pas prouvés)

1. **Tout le domaine vision n=large s'applique à n=500** — LeJEPA in-domain fait ses preuves à n≥1k ; notre n subsiste au-dessous de tout bench étudié. Gaffe au tune : full-batch SIGReg fait même maths de l'espace O(1/N), pas celui de la valeur.
2. **Littwin ρ-filtrage = absolute (linear)** — aucun théorème n'étend à transformers (leur propre p.11).
3. **Yu-Thm + couverture-actions** : à 100-500 exemples, la plupart des paires d'actions sont non-certifiées ; collapse partiel possible indétectable.
4. **LeJEPA isotrope-force = pire-cas** ; pour une task précise, l'isotropie n'est pas garantie optimale (Hypothèse "task gradients isotropes" en pratique fausse).

## 5. Rappel d'alineas

- Pool poolé precoumis : `data/landing/act2-pilot/refit-pool-v2.json` (111 patchs, hash dans ce file).
- Predictor act2-v2 (GBDT-action, LOTO-honest) : `governance/act2/arm-artifacts/predictor-act2-v2.json` — shadow act2-v1; poids 0.676.
- Code refit référence : `scripts/act2/refit_predictor_v3_gbdt.py` (à chainer quand track E1-E3 intègrent de nouvelles features).

> **Lecture des frères BB** (LeCun enfants-interna) : JEPA n'est pas un de plus architecture — c'est "la preuve que l'espace latent doit porter l'énergie". On sait ce que la littérature dit. Nous savons ce qu'elle ignore. Ce jargon est notre filet ; ne le perdons pas en suivre.
