# Verdict P13 — la géométrie ne lit pas le patch Python

**Fenêtre** : `governance/act2/window-p13-scamper-proposal.md` (liste de K = 13
variantes gelée avant le premier fit) · **Statut** : sur le corpus d'étude **P12**,
**G1 EXCLU définitivement · issue établie « G2 ou G3 », indéterminée** — la barre
du maximum est en cours de mesure ; elle ne peut pas changer l'issue G1, et elle
seule départage G2 de G3. G3 est la résolution **anticipée**, pas établie
· **Écrit le 2026-08-29, amendé le même jour après revue adversariale externe**.

Zéro appel LLM, zéro Docker, zéro réseau. 13 variantes jouées sur P12, 11 sur
w46 en contrôle positif.

## Ce que P13 mesure, et pourquoi ce n'est pas ce que mesuraient v39/v41

`persist` — « ce test était déjà rouge, il le reste » — sépare à lui seul les
paires INTRA où les deux tests n'ont **pas** le même statut au tour *a* :
**0,9059** en P12, **0,9136** en w46. Ces paires pèsent 70 % du total. Une
variante peut donc gagner du Δ global sans rien savoir faire de neuf.

La seule strate où la géométrie peut prouver quelque chose est celle où
`persist` est **aveugle** — même statut des deux côtés, baseline 0,5000 **par
construction**. C'est la métrique primaire de cette fenêtre :

- **AUC⊥** — paires INTRA où `persist(a) == persist(b)`. 121 paires en P12,
  54 en w46. Contrôle de construction passé : l'AUC⊥ de `persist` vaut
  exactement 0,5000 sur les deux corpus (`scripts/act2/p13_metrics.py`).
- **AUC⊥⊥** — sous-strate « même test, tours différents ». En P12 elle porte
  **105 des 121 paires (86,8 %)** : seul le patch change. C'est littéralement
  `compare_patches`.

**La question de la fenêtre se réduit donc à une seule** : *le plongement d'un
patch distingue-t-il, pour un même ticket et un même test, une tentative qui
laisse le test rouge d'une tentative qui le répare ?*

Corollaire de puissance, contre-intuitif : sur cette question **P12 est mieux
doté que w46** — 121 paires aveugles contre 54, 105 « compare_patches » contre
20, 31 instances contributrices contre 8.

## Les 13 variantes

| id | axe | w46 ⊥ | **P12 ⊥** | P12 ⊥⊥ |
|---|---|---|---|---|
| V1 | complet 1540 d, `C` dans le pli | 0,7407 | 0,3802 | 0,39 |
| V2 | Ed (diff) + scalaires | 0,6667 | 0,3636 | 0,39 |
| V3 | Et (nom du test) + scalaires | 0,5926 | **0,5207** | 0,51 |
| V4 | PCA(Ed) ⊕ PCA(Et) dans le pli | 0,7963 | 0,4132 | 0,42 |
| V5 | fusion tardive 6 d | 0,5185 | 0,4876 | 0,50 |
| V6 | complet sans `frac` ni `turn` | 0,8519 | 0,4711 | 0,48 |
| V7 | cos test↔**hunk** (distribution) | 0,6111 | 0,4711 | 0,49 |
| V8 | Et → **corps du test** (`test_patch`) | — | 0,4132 | 0,44 |
| V9 | Ed → **diff AST-normalisé** | **0,7963** | 0,4504 | 0,46 |
| V10 | AST ⊕ corps du test | 0,7963 | 0,4421 | 0,47 |
| V11 | **logistique conditionnelle intra** | **0,9444** | 0,3884 | 0,40 |
| V12 | fit stratifié par `persist` | 0,5926 | 0,4711 | 0,50 |
| V13 | conjoint w46+P12 (DW-37) | — | 0,4628 | 0,50 |
| | *référence C=50, avant P13* | *0,8333* | *0,4793* | *0,50* |

**P12** : min 0,3636 · médiane 0,4504 · **max 0,5207** · **12 des 13 sous 0,50**.
**w46** : min 0,5185 · médiane 0,7407 · **max 0,9444** · aucune sous 0,50.

## Le verdict

**G1 est exclu sans avoir besoin de la barre.** La grille gelée exige, pour G1,
un AUC⊥ **≥ 0,65 en absolu**. Le meilleur des treize vaut **0,5207**. Ce critère
est inconditionnel : aucune mesure ultérieure ne peut le renverser.

**L'issue établie est « G2 ou G3 », et rien de plus fin.** Départager G2 de G3 demande la barre — le 95ᵉ centile du
maximum des K variantes sous permutation intra-instance — dont la mesure tourne
(100 permutations, `scripts/act2/p13_nulle.py`, artefact
`nulle-du-max-p12.json`). Deux repères en attendant, à ne pas lire comme des
barres : le tirage de permutation disponible du contrôle négatif rend **0,5372**
sur cette même strate, au-dessus du meilleur observé ; et la nulle du maximum
est **par construction supérieure** à celle d'une variante isolée. Le verdict
sera fixé à la valeur mesurée, non à cet argument. **Écrire « G3 » avant cette mesure serait anticiper sur ce que le texte déclare lui-même décisif** — objection soulevée par la revue adversariale du 2026-08-29 et retenue.

## Le motif « 12 des 13 sous 0,50 » n'est pas un signe — mesuré, pas raisonné

La table invite une lecture de trop : douze valeurs sur treize sous le hasard,
cela ressemble à un classement systématiquement inversé, donc à un signal porté
à l'envers. Un test binomial naïf appuierait — 12/13 rend p ≈ 0,003 bilatéral.

**Ce test serait faux, et il l'est pour la raison qui fonde toute cette fenêtre** :
les treize variantes ne sont pas indépendantes. Elles partagent le corpus, les
plis, et pour l'essentiel les mêmes features. Elles bougent en bloc.

La nulle par permutation le chiffre directement, puisqu'elle conserve par
construction la structure de corrélation :

| statistique | P12 observé | w46 observé | nulle w46, 60 tirages |
|---|---|---|---|
| variantes sous 0,5000 | 12/13 | 0/11 | **≥ 10/11 dans 25 % des tirages** |
| moyenne des AUC⊥ | 0,4412 | 0,7189 | 0,4743 ± 0,0892 · IC [0,297 ; 0,649] |

Un balayage de dix variantes sur onze du même côté de 0,50 arrive **un tirage
sur quatre** sous l'hypothèse nulle. Le motif de P12 est donc banal : il n'y a
pas d'anti-classement à expliquer, et rien à récupérer en retournant un score.

La moyenne, elle, sépare les deux corpus : P12 à 0,4412 est en plein dans la
nulle, w46 à 0,7189 est au 100ᵉ centile de la sienne. Le contrôle positif fait
son travail ; le corpus d'étude, non.

**Réserve de portée.** Cette calibration emprunte la nulle de w46 (K = 11, un
dépôt) pour juger une statistique de P12 (K = 13, trois dépôts). Elle établit le
**phénomène** — des variantes corrélées balaient ensemble — et non un p pour
P12. La nulle P12 en file rendra le chiffre propre à ce corpus.

## Ce que le G3 dit — et ce qu'il ne dit pas

**Il ne dit pas « on n'a pas trouvé ».** Les trois familles d'explication ont été
éliminées par mesure, chacune avec son contrôle positif sur w46 :

| famille | ce qui a été testé | résultat |
|---|---|---|
| **capacité** | PCA dans le pli, retrait de `frac`/`turn`, fusion tardive, `C` dans le pli | rien ne récupère rien en P12 ; sur w46 les mêmes gestes portent 0,8333 → **0,8519** |
| **objectif** | logistique conditionnelle intra-instance : on entraîne enfin le classement qu'on mesure | P12 0,3884 ; w46 0,8333 → **0,9444** |
| **représentation** | cos par hunk, corps du test, diff AST-normalisé | P12 0,41–0,47 ; sur w46 l'AST porte le diff brut de 0,6667 à **0,7963** |

**Les représentations font ce qu'on attend d'elles là où il y a du signal, et
rien en Python.** C'est ce qui transforme le résultat en fait mesuré.

**La tâche n'est pas mal posée.** Sur les 105 paires ⊥⊥ de P12 : **zéro diff
textuellement identique**, similarité médiane 0,694 — indistinguable de w46
(0,706). Les deux patchs diffèrent réellement.

**Deux axes fermés par mesure**, sur les DEUX corpus :

- **métadonnées du diff** — recouvrement stem du fichier de test ↔ fichiers
  touchés, même répertoire, nombre de fichiers, taille, « touche un fichier de
  test » : toutes entre 0,44 et 0,53 sur la strate aveugle ;
- **prédicteurs triviaux** sur la sous-strate ⊥⊥ : `turn` 0,5238, `frac` 0,4952,
  taille du diff 0,5571. Le sous-hasard systématique de P12 n'est donc pas une
  variable évidente prise à l'envers.

**Limites déclarées AVANT lecture, et tenues** : le canal par test est
structurellement inerte sur 86,8 % de la strate aveugle, où les deux lignes
partagent le même test — V8 et V10 n'y agissent que par le terme croisé ; et
V8/V10 n'ont **aucun contrôle positif**, les transitions v39 ne portant pas de
`test_patch`.

## Le résultat positif — V11, et il est pour le modèle servi

**En attente de sa nulle** (mesure en cours, w46, 100 permutations). Sous cette
réserve :

Le modèle servi est une **logistique pointwise poolée**, alors que la métrique
— et le produit — sont un **classement dans l'instance**. L'intercept
d'instance, que l'AUC INTRA annule, était appris comme du signal. V11 corrige ce
désaccord : Bradley-Terry sans intercept sur les différences de features
intra-instance.

| | w46 ⊥ | w46 ⊥⊥ |
|---|---|---|
| référence servie (C=50) | 0,8333 | 0,80 |
| **V11 conditionnel** | **0,9444** | **0,90** |

IC95 [0,75 ; 1,00] — 54 paires, **8 instances contributrices**. Le point est net,
l'intervalle est large. Rien ne doit être promu avant la nulle **et** un
élargissement de la population w46.

## Découverte tardive — le contrôle positif est UN dépôt, pas « JS/TS »

Trouvée en stressant la fondation par jackknife, après l'écriture du verdict.
Elle ne change aucune mesure ; elle change ce qu'elles autorisent à dire.

**Les 8 instances contributrices de w46 sont TOUTES `vuejs/core`.** Sur la strate
aveugle, elles sont 6, toutes `vuejs/core` également. Décomposition de la
population des 70 instances / 747 lignes :

| famille | instances | lignes | ≥ 2 tours | **issue mixte** | **paires aveugles** |
|---|---|---|---|---|---|
| `vuejs/core` | 15 | 137 | 14 | **8** | **54** |
| `iamkun/dayjs` | 11 | 15 | 1 | 0 | 0 |
| synthétiques kimi/qwen/epv | 44 | **595** | 32 | 0 | 0 |

Une instance ne peut contribuer que si elle a une **issue mixte** — au moins un
test rouge ET un test vert. Sans cela aucune paire (positif, négatif) n'existe en
son sein. **595 des 747 lignes — 80 % du corpus — appartiennent à une famille
synthétique qui ne produit aucune paire.** Elles gonflaient l'AUC poolée (défaut
déjà traité par l'erratum du 2026-08-29) et n'apportent rien à la discrimination
par test.

Trois conséquences :

1. **La question de l'arc était mal énoncée.** Ce n'est pas « JS/TS contre
   Python » : c'est **`vuejs/core` contre trois dépôts Python**. Le corpus de
   référence n'a jamais démontré la recette ailleurs que sur un dépôt.
2. **Le G3 en sort renforcé, et le succès w46 rétréci.** P12 porte 121 paires
   aveugles sur **28 instances de 3 dépôts** ; w46 en porte 54 sur **6 instances
   d'un seul**. Le seul des deux corpus à offrir une diversité de dépôts est
   celui qui échoue — et il échoue sur les trois.
3. **Défaut de conception de cette fenêtre, à mon compte.** La grille gelée exige
   pour G1 un leave-one-repo-out ≥ 0,60 sur chaque dépôt retiré. Ce critère est
   **structurellement insatisfiable sur le contrôle positif** : la strate aveugle
   de w46 n'a qu'un dépôt. J'ai gelé pour P12 une exigence de généralisation que
   la référence elle-même ne pourrait jamais franchir. Le verdict n'en dépend pas
   — G1 tombe sur le seuil absolu de 0,65, bien avant le LORO — mais l'asymétrie
   du critère est un défaut et doit être corrigée dans toute fenêtre future.

**Robustesse, en revanche : bonne.** Jackknife par instance sur la strate
aveugle de w46, retrait de la plus lourde (`vuejs__core-9572`, 22 des 54 paires) :

| bras | tout | pire retrait |
|---|---|---|
| complet C=50 (servi) | 0,8333 | 0,7812 |
| Ed C=50 | 0,8704 | 0,8125 |
| V6 | 0,8519 | 0,8125 |
| V11 | 0,9444 | **0,9302** |

Aucun retrait ne passe sous 0,60. Le signal `vuejs/core` est réel et stable —
il est simplement établi sur un seul dépôt.

**Ce que la disclosure servie doit encore dire.** Elle indique aujourd'hui que
89 % des instances de w46 n'ont aucune discrimination par test à faire. C'est
vrai mais insuffisant : elle ne dit pas que **les 11 % restants sont un seul
dépôt**. Correction à porter — modification visible en production, non poussée,
en attente de l'owner.

### Durcissement après revue adversariale externe — le contrôle positif est circulaire

La section ci-dessus dit que le succès de w46 vient d'un seul dépôt. La revue
adversariale du 2026-08-29 rend la formulation plus dure, et elle est exacte.

Ventilation revérifiée, corpus w46 : 747 lignes, 70 instances.

| famille | lignes | instances | lignes à label positif |
|---|---|---|---|
| synthétiques | 595 | 44 | **0 (0,0 %)** |
| `vuejs/core` | 137 | 15 | 30 (21,9 %) |
| `iamkun/dayjs` | 15 | 11 | **0 (0,0 %)** |

Strate aveugle : **54 paires, 6 instances, toutes `vuejs/core`**.

**`vuejs/core` n'est pas le dépôt où la méthode réussit : c'est le seul endroit
de w46 où la métrique existe.** Les deux autres familles n'ont aucun label
positif, donc aucune paire, donc ni succès ni échec mesurés. Le contrôle positif
ne pouvait pas sortir autrement — il valide la méthode sur l'unique population
où elle est évaluable. Ce n'est pas un succès localisé, c'est **un succès non
falsifiable**.

Ce que le contrôle autorise, exactement : la méthode atteint sa métrique sur la
strate intra-instance de `vuejs/core` — 6 de ses 15 instances, 54 paires. Un
dépôt, un langage, un type de dépôt.

Ce qu'il n'autorise pas : généraliser aux frameworks (n = 1 dépôt), au JS/TS
(`dayjs` n'a jamais été évalué), au Python, ni **étendre au-delà de ce périmètre
la licence d'interpréter un échec ailleurs comme un échec de la méthode**.

**Conséquence sur la disclosure.** La seconde correction non poussée doit dire
non pas « les 11 % d'instances restantes sont un seul dépôt », mais que **le
support entier de la métrique dans le corpus de référence est un seul dépôt, par
construction**. La première formulation décrit une concentration ; la seconde
décrit une impossibilité de réfutation. Elles ne disent pas la même chose.

### Ce qui ne discriminerait PAS l'hypothèse « framework »

À geler avant d'ouvrir le bras Django, sous peine de rejouer la circularité :

| expérience | pourquoi elle ne tranche pas |
|---|---|
| ajouter React/Next et constater un succès | **par construction**, si ces dépôts sont les seuls à porter des positifs |
| ajouter des dépôts type `dayjs` et constater leur contribution nulle | sans positifs ils sont hors strate — **une absence de score n'est pas un échec** |
| opposer w46 au corpus Python | confondu : langage, type de dépôt et composition varient ensemble |
| agréger w46 par famille | descriptif ; la strate reste entièrement `vuejs/core` |
| répliquer dans le seul écosystème Vue | ne sépare pas « effet framework » de « idiosyncrasie de `vuejs/core` », n = 1 |

**Condition d'ouverture du bras Django, gelée ici** : les deux bras — framework
et non-framework — doivent avoir une strate aveugle **non vide, vérifiée avant
le fit**. Comparer un bras scoré à un bras sans positifs, c'est comparer un
nombre à une absence.

## Correctifs de protocole issus de P13

0. **Compter les instances à ISSUE MIXTE avant d'ouvrir une fenêtre**, et les
   ventiler par dépôt. C'est la seule population qui porte la métrique ; le
   nombre de lignes ne dit rien. Un critère de généralisation (LORO) ne doit pas
   être gelé sans vérifier que le contrôle positif peut le satisfaire.
1. **Rapporter l'AUC⊥ en primaire** pour toute fenêtre transition. L'AUC INTRA
   globale reste diluée par une strate où `persist` seul fait 0,91.
2. **Choisir un hyperparamètre au critère de log-vraisemblance dans le pli
   DÉGRADE** l'AUC⊥, sur les deux corpus (w46 V1 0,7407 contre 0,8333 à `C=50`
   fixe ; V2 0,6667 contre 0,8704 ; P12 V1 0,3802 contre 0,4793). Le critère est
   calculé sur toutes les lignes d'entraînement, dont 70 % appartiennent à la
   strate où `persist` suffit : la CV interne optimise la strate facile.
   **Un critère de sélection doit porter sur la strate que l'on cherche à
   gagner.** Sélectionner `C` au critère AUC⊥ des plis internes serait légitime
   — plis internes, aucun label d'évaluation — mais c'est une **variante hors
   liste gelée** : elle exige un amendement, elle n'a pas été jouée.
3. **La barre d'une recherche à K variantes est la nulle du MAXIMUM**, pas celle
   d'une variante isolée.
4. **Déclarer les limites structurelles avant de lire.** Les deux déclarées ici
   se sont vérifiées ; les écrire après aurait été une rationalisation.

## Portée

- **Le modèle servi n'est pas touché.** `transition-model-served.npz` et la
  disclosure de `predict_transition` restent en l'état.
- **P12 n'est pas élargi.** La vague 4 était conditionnelle à G1 ou G2 ; sous G3
  elle ne se déclenche pas. Élargir un corpus où treize représentations donnent
  la nulle ne ferait que resserrer un intervalle autour de zéro.
- **P11 redevient ce qu'il aurait dû être** : une question de généralisation,
  pas de produit. La sélection SWE-smith devra être écrite pour la puissance sur
  la strate aveugle — c'est elle qui borne tout, pas le nombre de lignes.
- **V11 ouvre une piste sur le corpus servi**, indépendante de Python, à
  instruire dans sa propre fenêtre.

## Défaut de grille : G1 n'a jamais été montrée atteignable

Trouvé par la revue adversariale externe du 2026-08-29, en durcissant une réserve
que j'avais déjà consignée (ledger 194) mais dont je n'avais pas tiré la
conséquence.

Le fait de conception est connu : **le contrôle positif w46 ne contient qu'un
dépôt**, alors que G1 exige un leave-one-repo-out « ≥ 0,60 sur chacun des 3
dépôts retirés ». J'en avais conclu que le critère était insatisfiable sur w46,
et que le verdict P12 n'en dépendait pas — ce qui reste vrai.

Ce que je n'avais pas vu : sur w46, la meilleure variante **franchit la barre**
(0,9444 contre 0,7484 à 60 tirages) **et** le seuil absolu de 0,65. Les deux
critères évaluables de G1 sont donc satisfaits, et la frontière G1/G2 y repose
**entièrement** sur la clause inévaluable.

**Conséquence : aucun corpus disponible ne peut rendre G1.** Le seul qui porte du
signal en est empêché par sa structure, pas par sa performance. La grille gelée
n'a donc jamais démontré qu'elle sait produire son verdict positif — elle n'a
été exercée que sur des issues négatives.

C'est exactement la faute que ce dépôt collecte : **un gate doit prouver la
fonction, pas la présence.** Un critère qu'aucun contrôle positif ne peut
franchir ne discrimine rien ; il se contente de n'avoir jamais dit oui.

Portée exacte, pour ne pas surcorriger :

| | |
|---|---|
| effet sur le verdict P12 | **aucun** — G1 y tombe sur le seuil absolu (0,5207 < 0,65), bien avant le LORO |
| effet sur la lecture de w46 | w46 n'est **pas classable** par la grille ; il reste un contrôle positif de *mesure*, jamais un cas testé de G1 |
| effet sur P14 | **réel** — R1/R2/R3 réutilisent le LORO, et P14 a bien 3 dépôts. Le critère y devient évaluable, donc il doit être borné avant le fit (voir la fenêtre P14) |

## Artefacts

| | |
|---|---|
| métriques et auto-test | `scripts/act2/p13_metrics.py` |
| banc de variantes | `scripts/act2/p13_variants.py` |
| représentations vague 2 | `scripts/act2/p13_features.py` · `features-p12.json` |
| nulle du maximum | `scripts/act2/p13_nulle.py` · `nulle-du-max-{w46,p12}.json` |
| synthèse | `scripts/act2/p13_synthese.py` |
| résultats | `data/landing/act2-pilot/night-harvest/py-p12/p13/p13-*.json` |
