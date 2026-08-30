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

## Gates COMPLETS et décision du propriétaire (2026-08-30, 12:08)

Rejeu terminé : **171/171 instances**, 304 trajectoires, 1120 tours retenus.

| gate | valeur | seuil | |
|---|---|---|---|
| D1 volume | 1009 lignes · 171 instances | ≥ 700 · ≥ 70 | OK |
| **D2 fidélité** | **84,4 %** sur le témoin (128 tours) | ≥ 70 % | **OK** |
| D2′ variance | 78,8 % d'instances mixtes (119/151) | ≥ 60 % | OK |
| D3 persist=0 | **63,9 %** | ≥ 80 % | **ÉCHEC** |
| D4 taux y=1 | 38,6 % (389 positifs) | reporté | — |
| D4′ paires aveugles | **809** | ≥ 121 | OK |
| D5 intégrité | 92,1 % | ≥ 90 % | OK |

### D2 valide la conception de P14, et il le fait par mesure

Le témoin de fidélité résout à **84,4 %** pendant que la population d'étude est à
**55,4 %** de tours verts. C'était l'argument d'ouverture de cette fenêtre — la
fidélité du harnais et la sélection de population sont deux métiers, et les
confondre avait coûté P12. Ce n'est plus une plaidoirie : les deux nombres sont
séparés et disent chacun ce qu'ils doivent dire.

### Composition de la strate réellement lue

| | P12 | **P14** |
|---|---|---|
| paires aveugles `persist = 0` des deux côtés | 120 (99,2 %) | **629 (77,8 %)** |
| paires aveugles `persist = 1` des deux côtés | 1 (0,8 %) | 180 (22,2 %) |
| paires « même test, tours différents » (⊥⊥) | 105 | **365** |

D3 mesure un taux **marginal** de 63,9 %. La strate que la métrique consomme est
à **77,8 %** de `persist = 0`, et elle en contient **629 contre 120** — soit
**5,2× plus** de paires que P12 n'en a jamais eu sur ce même sous-ensemble. Les
180 paires `persist = 1` ne polluent rien : elles forment une seconde sous-strate
aveugle que P12 n'avait pas (une seule paire).

### Le LORO devient lisible pour la première fois de l'arc

| dépôt | paires aveugles | instances | précondition gelée le 2026-08-29 |
|---|---|---|---|
| `python-pillow` | 463 | 23 | **LISIBLE** |
| `tobymao` | 215 | 58 | **LISIBLE** |
| `iterative` | 131 | 11 | **LISIBLE** |

Les trois dépôts passent. La clause qui n'avait jamais pu dire oui — ni sur w46
(6 instances), ni sur P12 (un seul dépôt lisible sur trois) — est enfin
évaluable, et elle l'est sans qu'aucun de ses seuils ait bougé.

### Décision — D3 reste ÉCHEC, le fit est autorisé

**Arbitrage du propriétaire, 2026-08-30.** Le fit est autorisé. **D3 n'est pas
déplacé, pas supprimé, pas re-scopé** : il reste écrit ÉCHEC ici et au ledger,
définitivement.

Motif de l'autorisation, et il est mesuré : D3 lit un taux marginal, pas la
strate que la métrique consomme, et sur cette strate P14 apporte 5,2× plus de
paires `persist = 0` que P12. Six gates sur sept passent, dont les deux qui
portent la thèse de la fenêtre (D2 fidélité, D2′ variance).

**Ce qui a été refusé** : superséder D3 par un gate sur la composition de la
strate aveugle. L'argument serait juste sur le fond, mais construire un seuil
après avoir vu le résultat qu'il doit valider est de l'ingénierie de seuil — la
faute condamnée trois heures plus tôt dans ce même document. Un gate qui vient de
dire non ne se réécrit pas ; on assume de passer outre, en le disant.

**Ce que l'échec de D3 laisse ouvert** : si le fit sur P14 rend un résultat
positif, la question « ce résultat tient-il aussi sous D3 satisfait ? » reste
entière et devra être instruite sur un corpus qui satisfait D3.

## Contrôle inter-machines : la métrique poolée ne se reproduit pas, la strate aveugle si (2026-08-30, 12:47)

Avant de jouer P14 sur `Kimsufi-standard`, `scripts/remote/controle_encodage.sh`
a écarté les caches d'embeddings fabriqués sur le Mac, **ré-encodé P12
intégralement sur le serveur**, puis refait tourner les deux bancs. Un seul
ré-encodage, deux métriques lues dessus — donc une comparaison contrôlée, pas
deux expériences.

**La strate aveugle se reproduit à l'identique.** Les huit valeurs de V11 et V6
— AUC⊥, AUC⊥⊥, strate informative, toutes paires — sont **identiques au 4e
chiffre** aux valeurs publiées : V11 ⊥ 0,3884 / ⊥⊥ 0,40 / informative 0,9582 /
toutes 0,7892 ; V6 ⊥ 0,4711 / ⊥⊥ 0,4762 / informative 0,9059 / toutes 0,777.

**L'AUC poolée ne se reproduit pas.** Le même ré-encodage rend, pour `p10_fit`
sur P12 :

| bras | Mac (publié 29/08) | serveur (30/08) | écart |
|---|---|---|---|
| complet (1540 d) | 0,5654 | **0,5617** | −0,0037 |
| Ed + scalaires | 0,5172 | **0,5093** | −0,0079 |
| Et + scalaires | 0,7286 | 0,7309 | +0,0023 |
| scalaires seuls | 0,8250 | 0,8252 | +0,0002 |
| persist seul | 0,5244 | 0,5244 | 0 |
| négatif globale | 0,6130 | 0,6132 | +0,0002 |
| négatif intra-instance | 0,6617 | 0,6615 | −0,0002 |

**La cause est identifiée et elle n'est pas un défaut de code.** Le fit épingle
`OMP_NUM_THREADS=1` dans ses workers (`p10_fit.py:181`) et le bootstrap est semé
(`seed=42`, `p10_fit.py:170`) : à `X` identique, le résultat serait identique.
Ce qui diffère, c'est `X` — les embeddings jina, dont les composantes divergent
au 4e chiffre entre les deux machines (builds torch/BLAS distincts). La suite
est arithmétique : l'AUC poolée court sur **58 857 paires** dont 99,3 %
inter-instances, où des milliers de scores quasi ex æquo basculent ; l'AUC⊥
court sur **120 paires** de rang bien séparé, et absorbe la même perturbation
sans bouger d'un chiffre. `persist seul` — le seul bras sans embedding — ne
bouge pas du tout, ce qui ferme la boucle.

**Ce que ça fait à l'erratum du 29/08.** Son artefact scellé
(`erratum-auc-poolee-2026-08-29.json`) porte `poolee_observee = 0,5654` ; le
serveur en rend 0,5617. Contre une nulle intra-instance de moyenne 0,5240 et
d'écart-type 0,0677, la position passe de **+0,61 sd à +0,56 sd**. La conclusion
de l'erratum est inchangée et se trouve **renforcée** : une métrique dont le
chiffre de tête se déplace quand on change de BLAS n'est pas une métrique sur
laquelle on conclut. L'artefact n'est pas réécrit — il consigne une mesure faite
sur une machine donnée, et cette section dit laquelle.

**Ce qu'il ne faut pas en conclure.** Que l'AUC⊥ serait « la bonne » métrique.
Ce contrôle mesure sa **stabilité** sous une perturbation numérique, pas sa
validité. Une métrique constante peut être constamment fausse. Le seul acquis
est négatif et il porte sur l'autre : la poolée est trop fragile pour départager
quoi que ce soit à ce niveau d'écart.

**Portée du contrôle.** Il ne couvre pas les rejeux — aucun conteneur n'a été
rejoué sur les deux machines — ni la nulle du maximum, dont les 100 tirages P12
seront de provenance mixte (60 Mac, 40 serveur). Cette provenance mixte est
acceptable pour la même raison mesurée ici, l'AUC⊥ étant invariante ; elle est
consignée, pas tue.

## Fit P14 : les cinq bras et les deux contrôles (2026-08-30, 12:47)

Corpus construit sur le serveur de bout en bout : `X (1009, 1540)`, **168 plis**
LOO par instance, 819 transitions, 389 positifs, **strate aveugle 809 paires**.

| bras (AUC poolée — **non lisible**, cf. erratum) | P12 | P14 |
|---|---|---|
| complet (1540 d) | 0,5654 | 0,5930 |
| Ed + scalaires | 0,5172 | 0,6401 |
| Et + scalaires | 0,7286 | 0,6111 |
| scalaires seuls | 0,8250 | **0,7163** |
| persist seul | 0,5244 | 0,5227 |
| négatif globale | 0,6130 | **0,5435** |
| négatif intra-instance | **0,6617** | **0,5561** |

Deux faits, tous deux sur **l'instrument** et aucun sur le modèle.

**Le plancher a baissé, de 0,6617 à 0,5561.** C'est l'effet attendu de la règle
de sélection : la contamination inter-instances de la poolée vient du décalage
d'intercept entre plis, piloté par des taux de positifs très inégaux d'une
instance à l'autre. À 38,6 % de positifs au lieu de 5 %, ces décalages se
resserrent. Le banc fabrique moins d'AUC à partir de rien — c'est la thèse de la
fenêtre, vérifiée sur le contrôle négatif et non sur le résultat.

**Le raccourci trivial a faibli, de 0,8250 à 0,7163.** En P12, `persist/frac/turn`
seuls classaient presque parfaitement : un corpus à 5 % d'échecs se prédit par le
numéro de tour. Le raccourci est réduit, **pas éliminé** — 0,7163 reste le bras
le plus haut, loin devant les trois bras à embeddings.

**Ce que ça ne dit pas.** Rien sur la géométrie. Les trois bras à embeddings
— 0,5930, 0,6401, 0,6111 — sont à moins de 0,09 au-dessus du plancher
intra-instance, et `persist seul` (0,5227) est **sous** ce plancher. Sur une
métrique que l'erratum déclare invalide, et dont la section précédente vient de
montrer qu'elle bouge de 0,008 en changeant de machine, ces écarts n'autorisent
aucune conclusion. Le verdict R1/R2/R3 se lit sur l'AUC⊥ des 13 variantes
gelées, et sur rien d'autre.

## Vague 1 interrompue sur V7, et le script l'a lue comme un succès (2026-08-30, 13:52)

**Le défaut, avant le résultat.** `p13_variants --variantes V1..V13` est mort sur
**V7** en réclamant `_E-p14-hunkagg.npy`, absent : les représentations de la
vague 2 (`corps`, `ast`, `hunks`) n'avaient jamais été construites pour P14.
Le message d'erreur était explicite et disait quoi lancer. **Le pipeline ne l'a
pas lu** — `scripts/remote/p14_pipeline.sh` ne testait le code de sortie que de
sa première étape. Il a donc enchaîné sur V14, puis lancé la **nulle du maximum
de treize variantes dont sept n'existaient pas**.

C'est la même classe de défaut que les 58 instances perdues dans la nuit du 29
au 30/08 : un échec qui se lit comme un succès. La nulle a été tuée à 13:51,
douze minutes après son lancement ; aucun `nulle-partielle-p14.json` n'avait
encore été écrit, donc **aucun artefact n'est pollué**.

**Deux correctifs, pas un.** (a) Chaque étape des deux scripts lève désormais sur
un code de sortie non nul. (b) `p14_pipeline2.sh` ajoute une **garde de
dénombrement** : il compte les lignes de variante dans les journaux et refuse de
lancer la nulle si elles ne sont pas treize. Un garde qui compte le résultat vaut
mieux qu'un garde qui suppose que l'étape d'avant a réussi.

### Les six variantes calculées, toutes à la nulle

| variante | P12 ⊥ (121 paires) | **P14 ⊥ (809 paires)** | P14 ⊥⊥ |
|---|---|---|---|
| V1 complet 1540 d | 0,3802 | 0,4549 [0,3294 ; 0,5559] | 0,4932 |
| V2 Ed + scalaires | 0,3636 | 0,5179 [0,3290 ; 0,6062] | 0,4822 |
| V3 Et + scalaires | 0,5207 | 0,4969 [0,4212 ; 0,5659] | 0,5233 |
| V4 PCA(Ed) + PCA(Et) | 0,4132 | 0,4561 [0,3326 ; 0,5613] | 0,5068 |
| V5 fusion tardive 6 d | — | **0,5402** [0,3957 ; 0,6184] | 0,5315 |
| V6 V1 sans frac ni turn | 0,4711 | 0,4549 [0,3453 ; 0,5711] | 0,5151 |

Maximum provisoire **0,5402 (V5)**, intervalle enjambant 0,50. Les six
intervalles enjambent 0,50.

**Ce que ces six ne permettent pas.** Aucune lecture R1/R2/R3. La grille juge le
**maximum des treize** contre la barre du maximum des treize ; un maximum sur six
comparé à une barre sur treize serait conservateur, et comparé à une barre sur
six ne serait plus le protocole pré-enregistré. On attend les sept manquantes.

**Ce qu'elles confirment, en revanche**, et c'est indépendant de la grille : les
strates triviales se sont effondrées. La strate informative passe de 0,9059 à
**0,6485**, identique pour V1 à V6 — elle est dominée par `persist`, présent dans
tous les modèles, donc quasi invariante par variante, exactement comme en P12 où
V1, V2 et V4 rendaient un 0,9059 commun. Les paires « toutes » passent de
0,75–0,79 à 0,54–0,59. Avec le plancher intra-instance à 0,5561 et le raccourci
scalaire à 0,7163, cela fait **quatre mesures indépendantes** disant que la
population P14 ne se prédit plus par le numéro de tour.

**Reprise en cours** : `p13_features.py --corpus p14`, puis V7 à V13, puis la
nulle du maximum, puis la reprise des 40 tirages P12. Chaque étape lève.

## Les treize variantes, le LORO, et R2 exclu avant la nulle (2026-08-30, 16:00)

### Les treize, sur la strate aveugle de P14 (809 paires)

| variante | ⊥ | IC95 | ⊥⊥ |
|---|---|---|---|
| V1 complet 1540 d | 0,4549 | [0,3294 ; 0,5559] | 0,4932 |
| V2 Ed + scalaires | 0,5179 | [0,3290 ; 0,6062] | 0,4822 |
| V3 Et + scalaires | 0,4969 | [0,4212 ; 0,5659] | 0,5233 |
| V4 PCA(Ed) + PCA(Et) | 0,4561 | [0,3326 ; 0,5613] | 0,5068 |
| V5 fusion tardive 6 d | 0,5402 | [0,3957 ; 0,6184] | 0,5315 |
| V6 V1 sans frac ni turn | 0,4549 | [0,3453 ; 0,5711] | 0,5151 |
| V7 cos test↔hunk | 0,5760 | [0,4432 ; 0,6421] | 0,5260 |
| V8 Et → corps du test | 0,5624 | [0,3584 ; 0,6577] | 0,5068 |
| V9 Ed → diff AST-normalisé | 0,3758 | [0,2980 ; 0,5317] | 0,4712 |
| V10 AST + corps du test | 0,5080 | [0,3330 ; 0,5927] | 0,4959 |
| V11 logistique conditionnelle | 0,5340 | [0,3540 ; 0,6175] | 0,4767 |
| V12 fit stratifié par persist | 0,4104 | [0,3192 ; 0,5467] | 0,4904 |
| **V13 conjoint w46+P14 (DW-37)** | **0,6897** | **[0,5106 ; 0,7590]** | **0,5973** |

**V13 est le maximum, et c'est la seule des treize dont l'IC exclue 0,50.** Son
mécanisme est disclosé et sans fuite : w46 est **toujours** en entraînement, avec
une indicatrice de corpus, et l'évaluation ne porte que sur P14 ; le LOO par
instance de P14 est préservé. Ajouter le corpus JS/TS à l'entraînement fait
passer la strate aveugle Python de ~0,50 à 0,6897.

Cet IC ne se lit pas seul : V13 est le **maximum de treize** représentations
cherchées. C'est précisément l'objet de la barre du maximum, qui tourne.

### LORO — lisible sur les trois dépôts, et aucune variante ne le satisfait

Le correctif de sélection a rendu le critère évaluable : `iterative` 131 paires /
11 instances, `python-pillow` 463 / 23, `tobymao` 215 / 58 — les trois au-dessus
de la précondition gelée le 29/08 (≥ 10 instances **et** ≥ 30 paires). En P12 les
trois étaient illisibles (69/18, 26/6, 26/4). **La précondition d'amendement n°1
est validée par la mesure, pas par l'argument.**

| variante | iterative | python-pillow | tobymao | dépôts ≥ 0,60 |
|---|---|---|---|---|
| V1 | 0,8397 | 0,6371 | 0,5209 | 2/3 |
| V2 | 0,8397 | 0,6134 | 0,5581 | 2/3 |
| V3 | 0,5649 | 0,6782 | 0,6093 | 2/3 |
| V6 | 0,8397 | 0,5788 | 0,5302 | 1/3 |
| V11 | 0,2519 | 0,5335 | 0,4558 | 0/3 |
| V14 | 0,2366 | 0,4212 | 0,4698 | 0/3 |

**Aucune variante couverte ne satisfait le critère sur les trois dépôts.**

**Réserve à ne pas taire** : `iterative` rend **exactement 0,8397** pour V1, V2 et
V6 — trois jeux de traits différents, quatre décimales identiques, sur 131 paires
(0,8397 × 131 = 110 paires concordantes tout rond). Trois designs qui atterrissent
sur le même 110/131 est un signe de classement dégénéré sur un petit ensemble
très ex æquo, pas une performance. Ce chiffre n'est pas exploité ici.

### Le code du LORO n'avait jamais été appelé

`loro()` a été écrit dans `p13_variants.py` le 29/08 avec sa précondition, puis
**jamais branché** : ni option CLI, ni appel dans `main()`. Le critère que R2
exige était du code mort pendant vingt-quatre heures. Il est branché par
`scripts/act2/p14_loro.py`, pilote **séparé** — la nulle du maximum importe
`p13_variants`, et modifier ce module pendant qu'elle tourne changerait le banc
sous ses pieds.

### R2 est exclu, et il l'est sans la barre

La grille gelée fait de R2 une **conjonction** : franchir la barre **ET** ≥ 0,65
absolu **ET** LORO ≥ 0,60 sur chacun des trois dépôts.

1. Une seule des treize atteint 0,65 : **V13**, à 0,6897. La deuxième est V7 à
   0,5760. Toutes les autres échouent le seuil absolu, quelle que soit la barre.
2. V13 n'est **pas couvert** par le LORO. `LORO_BLOCS` est gelé depuis le 29/08,
   avant le rejeu, et exclut V4, V5, V12 et V13 parce qu'un fit unique hors-dépôt
   n'y est pas le même objet — pour V13, « retirer un dépôt » est ambigu dès lors
   que l'entraînement mêle deux corpus aux dépôts disjoints. Cette couverture
   n'est **pas élargie après coup au vu du classement** : ce serait de
   l'ingénierie de critère, la faute déjà refusée sur D3.
3. Donc la conjonction de R2 ne peut être établie pour aucune variante.

**Les issues possibles se réduisent à R1 et R3** — R1 si V13 reste sous la barre
du maximum, R3 s'il la franchit. La barre décide, et elle seule.

**Ce que R3 vaudrait** : une piste, rien de servi — et une piste dont le
mécanisme est explicitement « il faut du JS/TS en entraînement pour prédire du
Python ». La question ouverte par l'échec de D3 reste entière par-dessus.

## Le garde d'épinglage des fils ne gardait rien — 5,5× de calcul perdu (2026-08-30, 19:56)

**Le défaut.** `p13_nulle._init` posait `OMP_NUM_THREADS=1`,
`OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1` dans l'*initializer* du pool,
c'est-à-dire **après** que `numpy` et OpenBLAS aient été chargés par le
processus parent. OpenBLAS lit ces variables **au chargement de la
bibliothèque**, jamais ensuite. Les quinze workers tournaient donc à **seize
fils chacun** sur des matrices 1009 × 1540 — assez petites pour que la
synchronisation des fils coûte plus cher que le calcul lui-même.

**Mesuré, avec les deux côtés du contrôle :**

| condition | V1 sur P14 | AUC⊥ rendue |
|---|---|---|
| mono-fil, épinglé dans l'environnement (MiscV2) | **158 s** | 0,4549 |
| multi-fil, 16 fils (Kimsufi) | **866 s** | 0,4549 |

**Le résultat est identique, le temps est 5,5× plus long.** Le compteur système
mentait dans le même sens : `ps` montrait 104 % de CPU par worker, ce qui donnait
l'illusion d'un cœur bien employé, alors que seize fils passaient l'essentiel de
leur temps à se synchroniser. Conséquence directe : en **2 h 56**, quinze workers
n'avaient pas terminé **un seul** des cent tirages.

**Le correctif** est dans l'environnement du lancement, avant tout import Python
(`scripts/remote/nulle_p14.sh`). Vérifié après relance : **1 fil par worker,
99,9 % de CPU**, charge retombée de 222 à 78 puis vers 15.

**Ce que ça ne change pas** : aucun résultat. Le nombre de fils modifie l'ordre
des réductions BLAS, donc les derniers bits, pas le classement — V1 rend 0,4549
des deux côtés. Les 60 tirages de la nulle P12 calculés sur le Mac l'ont été dans
le régime multi-fil : ils sont lents, pas faux, et cette provenance est écrite.

### Troisième garde de la journée qui n'était pas en vigueur

C'est un motif, pas une coïncidence :

| garde | ce qu'il promettait | ce qu'il faisait |
|---|---|---|
| `p14_pipeline.sh` | arrêter la chaîne sur un échec | ne testait le code de sortie que de l'étape 1 |
| `p13_variants.loro()` | évaluer le critère LORO de R2 | écrit, jamais appelé — ni CLI ni `main()` |
| `p13_nulle._init` | épingler les fils BLAS à 1 | posé après le chargement d'OpenBLAS |

Les trois sont du **code écrit pour être sûr, qui n'était pas en vigueur**. Aucun
ne levait, aucun ne se voyait à la lecture. La leçon opérationnelle est la même
que celle de `feedback_gate_must_prove_function` : un garde doit être vérifié par
une mesure qui échouerait s'il ne marchait pas — ici, compter les fils, compter
les variantes, lire le code de sortie.

### Seconde machine : MiscV2, validée par contrôle positif

`145.239.65.205` (`ns3086367`, 8 cœurs, 31 Go) héberge la pile de dev Acre —
huit conteneurs. Elle est engagée à **6 workers en `nice -n 19`**, deux cœurs
laissés à Acre, venv **strictement aligné** sur Kimsufi (Python 3.13.7,
numpy 2.5.2, scikit-learn 1.9.0, scipy 1.18.1) pour que les deux moitiés de la
nulle sortent du même estimateur.

Contrôle positif avant engagement : V7, V11 et V1 rejouées sur MiscV2 rendent
**exactement** les valeurs de Kimsufi, IC compris (V7 ⊥ 0,576 / V11 ⊥ 0,534 /
V1 ⊥ 0,4549). Partition par plage — Kimsufi `k ∈ [0, 71)`, MiscV2 `k ∈ [71, 100)`
— pour que les deux machines ne rejouent jamais le même tirage ; checkpoints et
rapports suffixés, fusion faite à la main après.

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
