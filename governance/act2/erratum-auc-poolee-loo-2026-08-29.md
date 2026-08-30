# Erratum métrologique — l'AUC poolée en LOO ne mesure pas la discrimination par test

**Statut : PROPOSÉ à l'owner le 2026-08-29.** · **Direction** : négative (erratum,
protocole `governance/erratum-protocol.md`) · **Artefact d'erratum** :
`governance/act2/arm-artifacts/erratum-auc-poolee-2026-08-29.json` (liste
d'invalidation + empreintes sha256) · **Artefact de mesure** :
`data/landing/act2-pilot/night-harvest/py-p12/erratum-auc-poolee-2026-08-29.json`
(sha256 `bb5b8046d3bf8341dd81fe231f23c695f8deec0dc189ddd47e4d51b6d5d2a7ed`) ·
**Reproduction** : `.venv/bin/python scripts/act2/erratum_auc_poolee.py`
(zéro appel LLM, ~25 min, n'écrit dans aucun artefact scellé).

## Le défaut

Toutes les fenêtres transition rapportent une **AUC poolée** : les prédictions
hors-pli des N plis sont concaténées, puis une seule AUC est calculée sur
l'ensemble.

L'AUC poolée compare donc des points notés par des **modèles différents** — un
par pli. L'intercept de chacun dépend du taux de positifs de son jeu
d'entraînement, qui change à chaque pli retiré. Ce décalage de niveau entre plis
n'a aucun rapport avec la question posée, et il contamine les paires
**INTER-instances** — lesquelles pèsent **99,3 %** des paires de l'AUC poolée
(58 449 sur 58 857 en P12 ; 21 375 sur 21 510 en w46).

Rien de tout cela ne se voit sans un contrôle négatif adapté. Une permutation
**globale** des labels ne le révèle pas : elle détruit aussi la structure par
instance, donc elle rend un plancher proche de 0,50 et rassure à tort. Il faut
permuter **dans chaque instance** — le taux de positifs de l'instance est alors
conservé, et toute AUC restante ne peut plus venir que de la capacité à classer
les instances entre elles.

## Ce que ça change, mesuré

20 permutations intra-instance par configuration, quatre configurations :

| corpus / plis | métrique | observée | nulle (moyenne) | écart-type | max des tirages | position |
|---|---|---|---|---|---|---|
| **w46 / trajectoire (89 plis)** | **poolée** | **0,9778** | **0,9484** | 0,0202 | 0,9738 | **+1,46 sd** |
| w46 / trajectoire | INTRA | 0,8296 | 0,4256 | 0,0826 | 0,6000 | **+4,89 sd** |
| w46 / instance (70 plis) | poolée | 0,9653 | 0,9290 | 0,0254 | **0,9760** | **+1,43 sd** |
| w46 / instance | INTRA | 0,9185 | 0,4781 | 0,0766 | 0,6815 | **+5,75 sd** |
| P12 / instance (152 plis) | poolée | 0,5654 | 0,5240 | 0,0677 | 0,6513 | +0,61 sd |
| P12 / instance | INTRA | 0,7843 | 0,5015 | 0,0799 | 0,7169 | **+3,54 sd** |

**La ligne qui compte est la première** : c'est la configuration exacte qui a
produit le chiffre servi. Sous permutation intra-instance, l'AUC poolée reste à
**0,9484** — le biais de la métrique vaut **+0,4484**. La valeur observée n'est
qu'à 1,46 écart-type de ce plancher, et en LOO par instance **un tirage sur
vingt a dépassé la valeur observée** (max 0,9760 contre 0,9653).

**L'AUC poolée ne distingue donc pas notre modèle d'un modèle qui se contenterait
de classer les tickets par risque**, sans rien discriminer test par test.

Note de portée : pour P12 les deux structures de plis coïncident, la clé de
trajectoire v39 `(instance, modèle)` se réduisant à l'instance sur un corpus à
solveur amont unique. Seule la comparaison w46 est informative sur ce point.

## La métrique de remplacement

**L'AUC INTRA** ne retient que les paires (positif, négatif) d'une **même
instance**. Les deux points y sont notés par le même modèle : le décalage de pli
s'annule exactement. Sa nulle est centrée où elle doit l'être — 0,4781 et 0,5015
selon la configuration, contre 0,9290 à 0,9484 pour la poolée.

C'est aussi la seule métrique qui corresponde au produit. `predict_transition`
rend une probabilité **par test** pour les tests déclarés d'**une seule**
instance ; la comparaison inter-instances qui porte 99 % de l'AUC poolée n'est
jamais faite en service.

Chiffres corrigés, LOO par instance, IC bootstrappés **par instance** (les paires
d'une même instance ne sont pas indépendantes) :

| bras | w46 INTRA | Δ vs `persist` | P12 INTRA | Δ vs `persist` |
|---|---|---|---|---|
| complet (1540 d) | **0,9185** | **+0,170** [+0,049 ; +0,355] | 0,7843 | −0,001 [−0,083 ; +0,119] |
| Ed (diff) | 0,8963 | **+0,148** [+0,023 ; +0,317] | 0,8113 | +0,026 [−0,053 ; +0,136] |
| Et (nom du test) | 0,7852 | +0,037 non signif. | 0,8333 | +0,048 [−0,010 ; +0,165] |
| `persist` | 0,7481 | baseline | 0,7855 | baseline |

**Le signal par test existe et il est solide** : +5,75 écarts-types au-dessus de
sa nulle sur w46, et le bras complet bat `persist` de +0,170 avec un IC qui
exclut zéro. Le modèle servi **n'est pas invalidé**.

Deuxième renversement, non trivial : sous la métrique valide c'est
**l'embedding du diff (Ed) qui porte le signal** (+0,148, significatif), pas
celui du nom du test (+0,037, non significatif). La métrique poolée disait
l'inverse — elle plaçait Et (0,9723) devant le bras complet (0,9653).

## Ce que l'erratum ne dit PAS

- Il ne dit pas que le modèle servi est sans valeur. Il dit que le nombre publié
  décrit une capacité — **classer les tickets par risque** — différente de celle
  qu'annonce une sortie par test.
- Il ne dit pas que la géométrie fonctionne en Python. Sur P12, aucun bras ne
  bat `persist` de façon significative. L'IC exclut en revanche un effet de la
  taille de celui de w46 (+0,170 est hors de [−0,083 ; +0,119]) tout en laissant
  **indécidable** un petit effet au seuil S2 de +0,05. Le verdict correct est
  « effet w46 exclu, petit effet indécidable », jamais « pas de signal ».
- Il ne remet pas en cause le finding A3 de v46 (`flip_R = 0/250`). **Relecture
  faite** — voir la section suivante : le verdict est démontré indépendant du
  seuil.

## Relecture d'A3 — verdict maintenu, et renforcé

Le seul point qu'A3 empruntait au pipeline poolé est son **seuil de Youden**, qui
servait à sélectionner les cas éligibles et à compter les bascules. Vérification
par balayage exhaustif de tous les seuils observables, sur les 250 cas gelés de
`data/landing/act2-pilot/w46/probe-results.json` :

| | valeur |
|---|---|
| `p_orig` sur les 250 cas | **une seule valeur distincte : 0,000** |
| `p_revert` sur les 250 cas | **une seule valeur distincte : 0,000** |
| meilleur `flip_R` atteignable, tous seuils confondus | **0,0000** |
| grille | A1 exige ≥ 0,60 · A2 exige ≥ 0,35 |

**Aucun seuil ne peut produire une seule bascule.** Le verdict A3 ne dépendait
donc pas du seuil, et la mise en cause tombe.

Deux remarques qui renforcent plutôt qu'elles n'affaiblissent :

1. Le fait que `p_orig` et `p_revert` soient **tous exactement 0,0** est la même
   pathologie que celle relevée au défaut n°2 de l'erratum du 2026-08-25 :
   l'isotonic aplatit tout en bas de son domaine. La colonne calibrée ne porte
   ici **aucune information**.
2. Le diagnostic d'A3 ne reposait heureusement pas dessus. Il est fait en
   **espace z brut, pré-isotonic**, donc hors de portée de tout défaut de
   calibration ou de seuil : `z_orig` médian −9,61 (intervalle [−13,76 ; −3,84]),
   `Δz` du revert médian **−0,153** — le mauvais sens — moyenne −0,229, et
   seulement 2 cas sur 250 au-dessus de +1. Inverser l'effet d'un patch déplace
   le score dans la mauvaise direction.

A3 est donc l'un des rares verdicts de cet arc qui traverse les deux errata
sans une égratignure.

## Portée descendante — liste d'invalidation (protocole §3)

La chaîne d'origine reste : rien n'est réécrit.

| artefact | sha256 | statut | portée |
|---|---|---|---|
| `arm-v41-transition-rejudg-verdict-2026-08-20.json` | `7fd42a8b…` | **NIVEAU INVALIDÉ**, verdict maintenu | `T1_auc.modele = 0,9931` est une AUC poolée : non interprétable comme discrimination par test. Corrigé en **0,9185 INTRA** (LOO instance). `T1` reste franchi — Δ +0,170 contre un seuil de +0,03. |
| `arm-v39-transition-verdict-2026-08-20.json` | `6e9c2224…` | **NIVEAU INVALIDÉ**, verdict maintenu | même défaut sur `T1_auc.modele = 0,9601`. Population de 152 paires, non recalculée ici : à requalifier si citée. |
| `transition-model-served.npz` | `3c4b5baa…` | **INTACT** — disclosure à corriger | les poids ne sont pas en cause. C'est le chiffre qui l'accompagne, et l'absence de mention de la métrique, qui doivent changer. |
| `arm-v46-e6-adversarial-verdict-2026-08-22.json` | `0aa82c6b…` | **RELU — INTACT** | balayage exhaustif des seuils : `flip_R = 0` pour **tout** seuil. Verdict A3 maintenu, et désormais démontré indépendant du seuil. |
| `T2_jaccard` de v39 et v41 | — | **NON RECALCULÉ** | le Jaccard s'appuie sur un seuil, pas sur un classement inter-plis ; il échappe *a priori* à ce défaut mais reste affecté par le seuil in-band (erratum du 2026-08-25, ledger 172). |

## Correctif de protocole

1. **Rapporter l'AUC INTRA** comme métrique primaire de toute fenêtre transition,
   et l'AUC poolée seulement en second, explicitement étiquetée « discrimination
   entre instances ».
2. **Le contrôle négatif doit permuter DANS le groupe de pli**, pas seulement
   globalement. Une permutation globale ne détecte pas ce défaut : elle a rendu
   0,5273 sur w46 là où la permutation intra-instance rend 0,9290.
3. **Rapporter le plancher de la nulle à côté de toute AUC**, jamais supposer
   0,50. Une AUC de 0,98 contre une nulle de 0,95 vaut moins qu'une AUC de 0,78
   contre une nulle de 0,50.
4. **Bootstrapper les IC par instance**, pas par paire : les paires d'une même
   instance ne sont pas indépendantes.
5. **Déclarer la puissance.** L'AUC INTRA repose sur les instances à issue mixte
   — 8 sur 70 en w46 (11 %), 31 sur 152 en P12 (20 %). Une fenêtre future doit
   sélectionner pour cette contrainte, pas la découvrir après coup.

Règle transverse dont ceci est une nouvelle occurrence, la deuxième en quatre
jours : *un gate doit prouver la fonction, pas la présence*. Ici une métrique
affichait 0,98 pendant que la capacité annoncée — discriminer test par test —
n'était pas celle qu'elle mesurait.
