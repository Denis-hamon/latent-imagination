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

## Amendement n°1 — quel corpus juge, quel corpus décrit (2026-08-30, avant tout fit)

La version scellée ce matin porte une incohérence que je lève avant de mesurer
quoi que ce soit, pour ne pas choisir l'interprétation en voyant les chiffres.

Le tableau de prédiction annonce des valeurs sur **w46 et P12**, tandis que le
protocole dit d'évaluer **sur P14, jamais avant**. Les deux ne peuvent pas être
vrais ensemble. Résolution :

| corpus | statut | pourquoi |
|---|---|---|
| **P14** | **décisif** — c'est lui que la grille S1/S2/S3 juge | labels **jamais vus**. V14 y est bien une hypothèse unique, donc **K = 1** et une nulle à une variante |
| w46, P12 | **descriptifs** — hors grille, jamais un verdict | leurs labels ont déjà été cherchés 13 fois. Y ajouter V14 en fait un **14ᵉ regard**, dont la barre honnête serait la nulle du max à K = 14, pas une nulle à K = 1 |

**Les valeurs de V14 sur w46 et P12 ne peuvent donc rien conclure**, ni dans un
sens ni dans l'autre. Elles servent à deux choses, et à rien d'autre :

1. **Contrôle de non-régression du code** — si on repasse à V14 les blocs de V11
   ou de V6, il doit rendre exactement leurs chiffres publiés.
2. **Vérifier que la prédiction scellée n'était pas absurde** avant de dépenser
   P14 dessus.

C'est la même règle que celle qui a fondé la nulle du maximum en P13 : **la barre
dépend du nombre de fois qu'on a regardé le corpus**, pas du nombre d'hypothèses
qu'on déclare.

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

## Résultat descriptif (2026-08-30, 09:58) — la prédiction scellée n'est pas tenue

Hors grille, par construction : ces deux corpus décrivent, ils ne jugent pas.

**Contrôle de non-régression : exact.** Après refactorisation de V11 en enveloppe
d'un cœur paramétrable, V11 et V6 reproduisent leurs chiffres publiés au
quatrième décimal sur les deux corpus — V11 ⊥ 0,9444 (w46) et 0,3884 (P12),
V6 ⊥ 0,8519 et 0,4711.

| | V11 (⊥) | **V14 (⊥)** | écart | ⊥⊥ V11 → V14 | informative V11 → V14 |
|---|---|---|---|---|---|
| w46 | 0,9444 | **0,9259** | −0,0185 = **1 paire sur 54** | 0,90 → 0,90 | 0,9383 → 0,9691 |
| P12 | 0,3884 | **0,5041** | +0,1157 = 14 paires sur 121 | 0,40 → 0,5238 | 0,9582 → **0,4530** |

**Sur w46, la prédiction « ≥ 0,9444 » n'est pas tenue.** Il faut le dire, et il
faut dire aussi de combien : **une seule paire sur 54**, très à l'intérieur de
l'IC95 [0,80 ; 1,00]. Traiter cet écart comme une réfutation serait aussi
malhonnête que d'avoir traité un gain d'une paire comme un succès. La lecture
juste est : **V11 et V14 sont indiscernables sur w46**.

**Sur P12, la prédiction « ~0,50, la nulle » est tenue** : 0,5041.

### L'erreur de mécanisme dans la fenêtre scellée

La colonne qui compte n'est aucune des deux prédites. Sur P12, V14 **effondre la
strate informative, de 0,9582 à 0,4530**.

La cause est directe : sur cette strate, `persist` **seul** vaut 0,9059. Le
retirer retire l'essentiel du signal. Le raisonnement que j'avais scellé —
« `persist` est constant dans la paire, donc il s'annule et ne fait que consommer
de la capacité » — **n'est vrai que sur la strate aveugle**. Le modèle
conditionnel est entraîné sur **toutes** les paires intra-instance, informatives
comprises, où `persist` ne s'annule pas et porte presque tout.

J'ai généralisé à l'entraînement un argument qui ne valait qu'au scoring, et sur
une sous-strate.

### Ce que cela change

**Les deux leviers ne se composent pas.** Le levier est l'objectif — V11 — et les
scalaires restent. La combinaison n'apporte rien sur w46 et détruit la strate
informative sur P12.

**V14 sera tout de même évalué sur P14**, comme pré-enregistré : le calcul coûte
quelques secondes, et refuser de jouer un test après avoir vu un descriptif
défavorable serait la même faute de sélection, dans l'autre sens.

L'attente honnête est désormais **S3**.

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

## Résultat V14 sur P14 — S1 est exclu, l'issue établie est « S2 ou S3 » (2026-08-30, 13:49)

Labels jamais vus, corpus P14 encodé de bout en bout sur le serveur :

| strate | V14 sur P14 | rappel V14 sur P12 |
|---|---|---|
| **⊥ (aveugle)** | **0,5204** IC95 [0,3434 ; 0,6082] | 0,4530 |
| ⊥⊥ (même test) | 0,5014 | — |
| informative | 0,4864 | 0,4530 |
| toutes | 0,5046 | — |

**S1 est exclu, et il l'est sans la nulle.** La grille scellée exige une
conjonction : franchir la nulle à une variante **ET** ≥ 0,65 en absolu. V14 rend
0,5204. L'échec du seuil absolu suffit seul à clore S1, quel que soit le résultat
de la nulle — c'est exactement le raisonnement que la revue externe avait tenu
sur G1 en P13, et il s'applique ici à l'identique.

**Ce qui reste indéterminé** : S2 exige de franchir la nulle à une variante, qui
n'est pas encore calculée sur P14. L'issue établie est donc **« S2 ou S3 »**, et
proposer S3 maintenant anticiperait sur une mesure que la fenêtre déclare
elle-même décisive. L'attente reste S3 — l'IC enjambe 0,50 sur les quatre strates
— mais une attente n'est pas un verdict.

**Le mécanisme scellé était faux, et P14 le redit.** La fenêtre prédisait que
retirer les scalaires ponctuels libérerait de la capacité sur la strate aveugle.
Sur P12, V14 avait effondré la strate informative de 0,9582 à 0,4530 sans rien
gagner ailleurs. Sur P14 le même effet se lit en plus net : la strate informative
tombe de **0,6485 (V1–V6, tous scalaires inclus) à 0,4864**, soit exactement la
nulle. Retirer `persist` ne redistribue pas de la capacité : cela supprime la
seule chose que le modèle savait faire.

