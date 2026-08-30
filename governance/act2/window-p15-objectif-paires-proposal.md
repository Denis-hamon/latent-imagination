# P15 — l'objectif, pas la représentation

**Statut** : PROPOSÉE · **Scellée le 2026-08-30, avant que P14 rende** · Hypothèse
unique, K = 1 · Aucune donnée nouvelle, aucun rejeu.

## Pourquoi maintenant, et pas après P14

P14 rejoue 171 instances et rendra dans la matinée. Écrire cette fenêtre **après**
avoir vu son résultat en ferait une pêche : on choisirait l'hypothèse qui colle.
Écrite avant, c'est un test. C'est la seule raison du calendrier.

## Ce que P13 a réellement appris

Treize variantes gelées ont testé des **représentations** : embeddings du diff,
du test, du diff AST-normalisé, du corps du test, PCA, fusion tardive, terme
croisé. Sur la strate aveugle, aucune n'a bougé en Python (max 0,5207) et le
classement sur w46 n'a pas été renversé par une représentation.

**La seule chose qui a déplacé le résultat est un changement d'objectif** : V11,
logistique conditionnelle intra-instance, 0,9444 contre 0,8333 pour le modèle
servi sur w46 — et 0,90 contre 0,80 sur le geste produit `compare_patches`.

## Le fait mesuré qui fonde cette fenêtre

Quatre mesures indépendantes, deux corpus, deux protocoles différents :

| comparaison | w46 (aveugle) | P12 (aveugle) |
|---|---|---|
| `Ed` seul vs modèle complet servi | **0,8704** > 0,8333 | **0,5372** > 0,4793 |
| `Et` seul vs modèle complet servi | 0,6296 < 0,8333 | **0,5455** > 0,4793 |
| V6 (sans `frac` ni `turn`) vs V1 | **0,8519** > 0,7407 | **0,4711** > 0,3802 |

**Les scalaires ponctuels dégradent le classement intra-paire**, et le gain de
leur retrait est répliqué sur les deux corpus (+0,111 sur w46, +0,091 sur P12
pour V6 contre V1).

Le mécanisme est explicite, pas inféré : sur la strate aveugle `persist` est
**constant dans la paire par construction** — il s'annule dans la différence et
ne peut rien classer, mais il consomme de la capacité au fit. `frac` et `turn`
varient dans la paire sans porter d'information sur le sort du test.

## L'hypothèse gelée — une seule

> **V14 = objectif par paires (V11) appliqué à la représentation sans scalaires
> ponctuels** — blocs `[Ed | Et | cos]`, sans `persist`, `frac` ni `turn`.

Les deux leviers mesurés sont orthogonaux et n'ont jamais été combinés. Aucune
autre variante n'est proposée ici. **K = 1**, et c'est délibéré : une hypothèse
unique pré-enregistrée se juge contre une nulle à une variante, pas contre la
nulle du maximum de treize.

## Ce qui est prédit, avant de mesurer

À écrire maintenant pour que l'échec soit lisible :

| corpus | prédiction | fondement |
|---|---|---|
| w46 | **≥ 0,9444** (au moins V11) | les deux leviers vont dans le même sens |
| P12 | **~0,50, la nulle** | V11 y vaut 0,3884, V6 0,4711 — aucun des deux ne sauve Python |

**Si P12 dépasse 0,60, la prédiction est fausse et c'est plus intéressant que le
succès attendu sur w46.** Une fenêtre qui ne prédit que ce qu'elle espère
n'apprend rien.

## Grille gelée

| issue | condition | conséquence |
|---|---|---|
| **S1** | V14 > sa nulle à une variante **ET** ≥ 0,65 absolu, sur P14 | l'objectif est le bon levier. Ouvre une décision de service |
| **S2** | franchit sa nulle sans le seuil absolu | piste. Rien de servi |
| **S3** | sinon | l'objectif ne suffit pas non plus. Le plafond est ailleurs — voir « Ce que cette fenêtre ne résout pas » |

Le LORO n'entre pas dans cette grille : la précondition de lisibilité gelée dans
`window-p14-variance-proposal.md` s'applique telle quelle, et la clause est
reportée « non évaluable » plutôt que comptée comme un échec si elle ne se lit
pas.

## Ce que cette fenêtre ne résout pas

À dire d'avance, pour ne pas vendre S1 comme plus qu'il n'est.

**Le verdict A3 tient** : la sonde adversariale déterministe a mesuré
`flip_R = 0/250` — le signal **ne lit pas l'effet sémantique du diff**. Il lit
des corrélats de surface. Changer d'objectif réordonne l'usage de ces corrélats ;
cela ne fabrique pas une lecture du patch.

Les tentatives de représentation qui visaient précisément cette lecture ont été
jouées et ont échoué : diff AST-normalisé (V9, 0,7963 sur w46, **sous** `Ed`
seul à 0,8704), corps du test extrait du `test_patch` (V10, 0,7963). Normaliser
la forme du diff n'a pas fait apparaître le sens.

**Donc même un S1 laisserait le plafond en place.** Ce qui le lèverait est d'un
autre ordre — exécuter, ou représenter l'effet du patch et non son texte — et
n'appartient pas à cette fenêtre.

## Protocole

1. Ajouter V14 à `p13_variants.py`, sans toucher aux treize autres.
2. L'évaluer sur **P14** dès que le rejeu et les gates ont rendu, jamais avant.
3. Nulle à une variante, 100 permutations intra-instance, même machinerie que
   `p13_nulle.py`.
4. Contrôle de non-régression : rejoué sur P12 et w46, V14 doit reproduire
   exactement les chiffres du tableau ci-dessus pour V11 et V6 si on lui repasse
   leurs blocs — un banc qui change de réponse selon le corpus chargé serait
   suspect.

## Hors périmètre

- **Le modèle servi n'est pas touché.** Aucune promotion avant que P14 ait dit si
  V11 tient sur trois dépôts. Promouvoir sur les 6 instances d'un dépôt unique
  serait rejouer la circularité documentée dans `window-p13-verdict.md`.
- **Aucune quatorzième variante de représentation.** Si S3 tombe, la réponse
  n'est pas une quinzième.
