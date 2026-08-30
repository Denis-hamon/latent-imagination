# Fenêtre P14 — sélectionner pour la VARIANCE de label, pas pour le volume

**Demandeur** : suite directe du verdict P13 (G3) et de la découverte
`vuejs/core`. Proposition rédigée le 2026-08-29, **liste et grille gelées avant
le premier rejeu**. Hôte `Kimsufi-standard`, zéro appel LLM.

**Question** : *le G3 de P13 tient-il sur un corpus sélectionné pour la variance
de label, où la population décisive est 4,6× plus grande ?*

## Le défaut corrigé, et il est explicite dans le code

`scripts/act2/p12_select.py:52` :

```sql
SELECT instance_id, n FROM agg WHERE n >= 4 AND r*1.0/n >= 0.75
```

**≥ 75 % de réussite exigés par instance.** Le gate D2 — un contrôle de
*fidélité du harnais* (« si rien ne se résout, c'est le rejeu qui est cassé ») —
a été appliqué comme un *filtre de population*. Deux métiers différents : la
fidélité se vérifie sur un témoin, la population d'étude se sélectionne pour la
variance.

Gisement des 3 dépôts : 469 instances, 4 852 trajectoires, 41 % résolues.

| bande de réussite par instance | instances | trajectoires | échecs |
|---|---|---|---|
| 0 % — jamais résolu | 209 | 2 086 | 2 086 |
| **]0 ; 100 %[ — mixte** | **153** | **1 683** | **769** |
| 100 % — toujours résolu | 101 | 1 065 | 0 |

| sélection | instances | trajectoires | échecs |
|---|---|---|---|
| P12, `r/n ≥ 0,75` | 155 | 1 692 | **81 (5 %)** |
| **P14, `0 < r < n`** | 153 | 1 683 | **769 (46 %)** |

**À coût de rejeu identique : 9,5× plus de patchs qui échouent.**

Rendement prévisible sans rejouer, mesuré sur P12 — **corrigé le 2026-08-29
avant le premier gate**. Une première estimation annonçait 85 % de rendement et
≈ 560 paires : elle reposait sur une définition plus étroite de « mixte »
(issue du dernier tour de chaque bloc, n = 13). Sous la définition que P14
utilise réellement — variation sur **l'ensemble des tours des blocs retenus** —
la coupe correcte, sur n = 42, donne :

| | P12 mesuré | P14 projeté |
|---|---|---|
| instances à blocs mixtes | 42 | **129** |
| rendement dans les mixtes | **67 %** (28/42) | 67 % |
| paires aveugles par instance mixte rejouée | 2,88 | 2,88 |
| **paires aveugles** | **121** | **≈ 371** |

Soit **3,1×**, et non 4,6×.

**Deuxième correction, après revue adversariale externe (GLM-5.3-Flash) et
stratification — le chiffre ponctuel n'est pas défendable.** Le relecteur a
signalé que les mixtes de P14 ne sont pas un échantillon aléatoire des mixtes de
P12. Vérification par stratification sur le nombre de tours en échec :

| échecs dans les blocs | P12 : instances | rendement | paires/inst | P14 : instances |
|---|---|---|---|---|
| 1 | 29 | 55 % | 1,97 | 35 |
| 2–3 | 13 | **92 %** | **4,92** | 45 |
| 4–8 | **0** | non mesuré | non mesuré | **49** |

Deux faits en découlent. **Le rendement n'est pas constant** : il croît fortement
avec le nombre d'échecs (55 % → 92 %, 1,97 → 4,92 paires). Les 67 % étaient une
moyenne sur un mélange. Et **38 % de la population de P14 est hors de toute plage
mesurée** : la bande 4–8 est vide en P12 *par construction*, le filtre
`r/n ≥ 0,75` avec `n ≥ 4` l'excluant mécaniquement.

Projection honnête, en fourchette et non en point :

- **plancher ≈ 290 paires** si la bande 4–8 était stérile — improbable au vu de
  la tendance, et cette valeur impute zéro à une bande non mesurée, ce qui est
  aussi arbitraire qu'imputer la moyenne ;
- **≈ 530 paires** si la bande 4–8 se comporte comme la bande 2–3 ;
- au-delà : **non mesuré**. P14 renseignera cette bande pour la première fois.

Le relecteur avait raison sur le mécanisme et s'est trompé de sens : il craignait
une chute vers 250, alors que la bande neuve est vraisemblablement la plus riche.
C'est la conséquence directe d'avoir retiré le filtre qui la supprimait.

**Le critère est NÉCESSAIRE, et c'est le résultat qui compte.** Coupe inverse,
plus puissante que la directe : **28 des 28 instances contributrices de P12
avaient des blocs mixtes (100 %)**, et les **110 instances non mixtes ont produit
exactement zéro** paire aveugle. P12 a donc rejoué 110 instances sur 152 —
**72 % de son budget** — sur une population structurellement incapable de
contribuer. P14 en gaspille **15 %** (23 sur 152).

**Les 209 jamais résolues sont exclues, et c'est symétrique.** Un test déclaré
rouge à tous les tours ne produit que des `y = 1` : aucune paire
(positif, négatif) intra-instance. Stérile dans l'autre sens.

## Règles gelées

1. **Sélection** : `n ≥ 4 AND r > 0 AND r < n`. Mêmes 3 dépôts, mêmes `K = 4`,
   `MAX_TRAJ = 2`, `MAX_DECLARED = 18` qu'en P12. **Seule la sélection change** —
   c'est ce qui fait de P14 un A/B propre contre P12.
2. **D2 re-scopé.** La résolution ≥ 70 % devient un contrôle de fidélité mesuré
   sur un **témoin de 20 instances `r = n`**, tirées déterministement, et jamais
   sur la population d'étude. Sur celle-ci, D2 est remplacé par un **gate de
   variance : ≥ 60 % des instances doivent présenter une issue mixte** après
   rejeu. D1, D3, D4, D5 sont inchangés.
3. **Aucune variante nouvelle.** P14 rejoue les **13 variantes gelées de P13**, à
   l'identique, avec la même métrique primaire AUC⊥ et la même nulle du maximum.
   Le corpus change, la grille ne bouge pas. Sans cette règle, P14 serait une
   nouvelle pêche et non un test de G3.

## Grille de décision — GELÉE

| issue | condition | conséquence |
|---|---|---|
| **R1 — G3 CONFIRMÉ** | le max des 13 reste sous la barre du maximum, sur ~560 paires aveugles | le G3 tient sur un corpus 4,6× mieux doté. Verdict Python solide, publiable |
| **R2 — G3 RENVERSÉ** | une variante franchit la barre **ET** ≥ 0,65 absolu **ET** LORO ≥ 0,60 sur chacun des 3 dépôts | P13 concluait sur un corpus trop pauvre : **erratum sur P13**, direction négative |
| **R3 — INDÉCIDABLE** | franchit la barre sans le LORO ou sans le seuil absolu | piste, rien de servi, rien de promu |

### Précondition de lisibilité du LORO — gelée le 2026-08-29, avant le premier fit

Le LORO est ici **satisfaisable en nombre de dépôts** — la population d'étude en
compte 3 (tobymao 90, python-pillow 43, iterative 38). Ce n'était pas le cas du
contrôle positif de P13, qui n'en avait qu'un.

Mais compter les dépôts ne suffit pas, et la ventilation de P12 le montre :

| dépôt | paires aveugles | instances contributrices |
|---|---|---|
| tobymao | 69 | 18 |
| python-pillow | 26 | 6 |
| iterative | 26 | **4** |

Les paires d'une même instance ne sont pas indépendantes — c'est la raison d'être
de la permutation intra-instance. **L'unité effective est l'instance, pas la
paire.** Un LORO lu sur un dépôt retiré qui n'apporte que 4 instances rend une
AUC dont l'intervalle avale largement l'écart entre 0,50 et le seuil de 0,60 : le
critère y échoue ou passe par bruit, pas par performance.

**Conséquence rétrospective** : le LORO était déjà illisible sur P12, non par
manque de dépôts mais par manque d'instances par dépôt. Le critère G1 n'était
donc atteignable sur **aucun** corpus de cet arc — voir la section « Défaut de
grille » de `window-p13-verdict.md`.

**Règle gelée ici, avant tout fit de P14** :

1. Un dépôt retiré n'est **lisible** que s'il apporte **≥ 10 instances
   contributrices ET ≥ 30 paires aveugles**. Les deux seuils sont fixés
   maintenant, sur la ventilation de P12 et sans connaître celle de P14.
2. Un dépôt non lisible est reporté **« non évaluable »**. Il n'est ni compté
   comme un succès ni comme un échec — les deux seraient des affirmations que la
   donnée ne porte pas.
3. Le LORO n'est déclaré **satisfait** que sur **au moins 2 dépôts lisibles**, et
   satisfait sur chacun des lisibles.
4. Si moins de 2 dépôts sont lisibles, la clause LORO est déclarée **non
   évaluable**, et l'issue est publiée comme **« R2 sous réserve LORO non
   évaluable »** — jamais rétrogradée en silence vers R3. Une clause qu'on ne
   peut pas lire ne doit pas se lire comme un échec.

Le point 4 est ce qui empêche la faute trouvée en P13 de se rejouer : une porte
qu'aucun contrôle ne peut franchir ne discrimine rien, elle se contente de ne
jamais dire oui.

## Amendement n°3 — D4 était structurellement insatisfiable sur P14

**Gelé le 2026-08-30 à 10:05, avant d'avoir lu la moindre statistique du rejeu
P14.** Le rejeu est en cours (118/171) ; aucune de ses valeurs n'a été consultée
pour écrire cette section, et les seuils ci-dessous viennent tous de chiffres
**déjà publiés** sur P12.

Le gate D4 de P12 exige un taux de positifs `y = 1` **entre 3 % et 15 %**. Cette
bande a été calibrée sur une population dont **5 % des trajectoires échouaient**
— celle que la règle `r/n ≥ 0,75` avait sélectionnée.

P14 sélectionne **pour la variance de label** : 46 % d'échecs dans le gisement.
Appliquer la bande de P12 ferait **échouer D4 précisément parce que P14 réussit
ce pour quoi il a été conçu.**

C'est le même défaut que celui trouvé hier sur G1 : *un gate doit prouver la
fonction, pas la présence*, et un gate qui ne peut pas dire oui ne discrimine
rien. Le corriger après avoir vu P14 échouer dessus aurait été un ajustement
post-hoc ; le corriger maintenant, en le déclarant, est une correction de
conception.

### Ce qui change, et d'où viennent les seuils

| gate | sur P12 | sur P14 | origine du seuil |
|---|---|---|---|
| D1 volume | ≥ 700 lignes, ≥ 70 instances | **inchangé** | intégrité, indépendant du corpus |
| **D2 résolution ≥ 70 %** | population d'étude | **témoin de fidélité seul** (19 instances `r = n`) | déjà gelé, amendement n°1 |
| **D2′ variance** | — | **≥ 60 % des instances d'étude à issue mixte** | déjà gelé, amendement n°1 |
| **D4 taux `y = 1`** | gate, bande 3–15 % | **reporté, PLUS un gate** | la bande mesure une propriété que P14 inverse volontairement |
| **D4′ paires aveugles** | — | **≥ 121** | **valeur publiée de P12**. P14 n'a de raison d'être que s'il en produit davantage |
| D3 persist=0 ≥ 80 % | | **inchangé** | intégrité |
| D5 intégrité ≥ 90 % | | **inchangé** | intégrité |

**D4′ est le gate qui compte réellement**, et c'est un progrès sur D4 : la
métrique ne consomme pas un taux marginal de positifs, elle consomme des
**paires aveugles**. Gater sur la quantité réellement consommée plutôt que sur
un proxy est ce que D4 aurait dû faire depuis le début.

Le seuil 121 n'est pas choisi : c'est le nombre de paires aveugles de P12,
publié dans `window-p13-verdict.md`. **Si P14 en produit moins, sa règle de
sélection est fausse et le corpus ne vaut pas d'être fitté** — c'est exactement
ce qu'un gate doit pouvoir dire.

## Lecture partielle des gates (2026-08-30, 10:46, rejeu à 136/171)

Lue **avant** la fin du rejeu, seuils déjà gelés et commités : cette lecture ne
peut rien ajuster. Le fit reste interdit tant que le rejeu n'a pas rendu.

| gate | valeur | seuil | |
|---|---|---|---|
| D1 volume | 779 lignes · 136 instances | ≥ 700 · ≥ 70 | OK |
| D2 fidélité | **non lisible** — témoin pas encore rejoué (0/19) | ≥ 70 % | en attente |
| D2′ variance | **77,0 %** d'instances à issue mixte (104/135) | ≥ 60 % | OK |
| D3 persist=0 | **63,0 %** | ≥ 80 % | **NON** |
| D4 taux y=1 | 40,2 % (313 positifs) | reporté | — |
| D4′ paires aveugles | **771** | ≥ 121 | OK |
| D5 intégrité | 92,9 % | ≥ 90 % | OK |

### La projection scellée était fausse — et par le plafond

P12 produisait **121** paires aveugles sur 154 instances. P14 en est à **771** sur
136, sans avoir fini : **6,4×**, très au-dessus de la fourchette **[290 ; 530]**
scellée le 2026-08-29.

La cause est exactement ce que j'avais déclaré non mesurable. Le rendement
observé :

| bande d'échecs dans les blocs | rendement mesuré | source |
|---|---|---|
| 1 échec | 1,97 paire/instance | P12, n = 29 |
| 2–3 échecs | 4,92 paire/instance | P12, n = 13 |
| 4–8 échecs | **~7,4** paire/instance | **P14, mesuré pour la première fois** |

La bande 4–8 comptait **zéro instance en P12**, exclue par construction par la
règle `r/n ≥ 0,75`. Elle pèse 38 % de P14 et rend davantage que les deux bandes
mesurées.

**Le refus d'extrapoler était juste ; la fourchette ne l'était pas.** La revue
adversariale craignait une chute vers ~250 et se trompait de sens ; mon propre
plafond de 530 se trompait aussi. Une fourchette bornée des deux côtés sur une
bande déclarée non mesurée reste une extrapolation — la seule écriture honnête
aurait été un plancher, sans plafond.

### D3 échoue, et n'est PAS déplacé

D3 exige que ≥ 80 % des lignes portent un test qui n'était **pas déjà rouge**.
P12 était à 93 % parce que ses trajectoires échouaient rarement. P14 sélectionne
pour l'échec : ses tests sont rouges plus souvent, et D3 tombe mécaniquement.

**C'est le même défaut structurel que D4, et je ne l'ai pas vu dans le même
passage.** L'amendement n°3, gelé à 10:05, écrit noir sur blanc « D3 inchangé —
intégrité, indépendant du corpus ». C'était faux : D3 dépend du corpus autant
que D4.

**D3 reste donc en échec.** Le corriger après l'avoir vu échouer serait
exactement l'ajustement post-hoc condamné trois heures plus tôt dans ce même
document. Un seuil ne se déplace pas parce qu'il vient de dire non.

Il existe un argument sérieux pour le re-scoper, et il est écrit ici pour être
jugé, pas appliqué : **la métrique se lit sur la strate aveugle, où `persist` est
constant dans la paire**. Un taux marginal de `persist = 0` plus bas change la
composition de cette strate sans l'invalider — D3 mesure une propriété que la
métrique n'utilise pas directement. Si cet argument est retenu, il doit l'être
par décision explicite du propriétaire, datée, et non par une réécriture
silencieuse du seuil.

**Autre écart à noter** : 66 tours non conformes contre 39 sur P12 — davantage de
patchs qui ne s'appliquent pas, cohérent avec une population choisie parmi les
trajectoires qui échouent.

## Hors périmètre

- **Le modèle servi n'est pas touché.** Les deux corrections de disclosure
  restent écrites et **non poussées**.
- **w46 n'est pas rouvert.** L'élargissement du corpus de référence est une
  fenêtre distincte, conditionnelle à la rétention de V11.
- **Django et les frameworks ne sont pas ouverts ici.** L'expérience
  discriminante (Python **et** framework) ne se lance qu'après que P14 ait prouvé
  le correctif de sélection.

## Artefacts

`scripts/act2/p14_select.py` · `p14-selection.json` + `p14-selection-freeze.json`
(sha256) · rejeu par `p12_replay.py` inchangé · gates par `p12_gates.py` ·
variantes par `p13_variants.py` · barre par `p13_nulle.py`.
