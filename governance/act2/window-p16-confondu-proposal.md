# Fenêtre P16 — casser le confondu langage × type de dépôt

**Statut : SCELLÉE le 2026-08-31, AVANT toute sélection et tout rejeu.**
**Direction** : discriminante. **Plan** : `~/.claude/plans/radiant-charting-lovelace.md`.
**Antécédents** : `window-p14-variance-proposal.md` (verdict R3),
`window-p13-scamper-proposal.md` (G3), `window-p15-objectif-paires-proposal.md` (S3).

## Le défaut que cette fenêtre attaque

| corpus | dépôts | **type de dépôt** | paires aveugles | résultat |
|---|---|---|---|---|
| w46 (JS/TS) | `vuejs/core` seul | **framework d'interface** | 54 | **marche**, p = 0,0198 |
| P14 (Python) | pillow, sqlglot, dvc | **bibliothèques et outil CLI** | 809 | échoue, 12 variantes sur 13 sous la barre |

**Langage et type de dépôt sont parfaitement confondus sur toute la campagne.**
Aucune mesure existante ne peut dire lequel des deux explique quoi. P16 fait
varier le **type de dépôt à langage constant**, en Python, où le matériel est
disponible sans un appel LLM.

## Règles GELÉES

Identiques à P14 — `K = 4` tours, `MAX_TRAJ = 2`, `MAX_DECLARED = 18`, règle
d'étude `n ≥ 4 AND 0 < r < n`, témoin de fidélité `n ≥ 4 AND r = n` (20
instances, tirage déterministe par `instance_id`). **Seule la composition en
dépôts change**, pour que P16 soit un A/B propre contre P14.

Source de trajectoires inchangée : `nebius/SWE-rebench-openhands-trajectories`.

### Bras FRAMEWORK — dépôts applicatifs, même nature que `vuejs/core`

| dépôt | rôle | instances mixtes (mesurées le 31/08) |
|---|---|---|
| `Textualize/textual` | framework d'applications TUI | 20 |
| `encode/starlette` | framework ASGI | 10 |
| `tornadoweb/tornado` | framework web | 5 |
| `falconry/falcon` | framework web | 3 |
| | | **38** |

### Bras BIBLIOTHÈQUE — appariement en volume

| dépôt | rôle | instances mixtes |
|---|---|---|
| `tox-dev/tox` | outil d'automatisation | 18 |
| `streamlink/streamlink` | bibliothèque + CLI | 17 |
| `PennyLaneAI/pennylane` | bibliothèque scientifique | 15 |
| `wemake-services/wemake-python-styleguide` | linter | 14 |
| | | **64** |

**`tobymao/sqlglot`, `python-pillow/Pillow` et `iterative/dvc` sont EXCLUS.** Ce
sont les trois dépôts de P14 : les réutiliser rendrait le bras bibliothèque non
indépendant d'un résultat déjà connu.

## Gate de puissance — DÉCLARÉ AVANT LE REJEU

Rendement mesuré sur P14 : **4,7 paires aveugles par instance mixte**.
Projection brute : bras framework ≈ 180 paires, bras bibliothèque ≈ 300.

> **Un bras qui rend moins de 54 paires aveugles — le compte exact de w46 — est
> déclaré NON ÉVALUABLE, jamais négatif.**

Sous ce seuil, un bras ne peut pas réfuter ce que w46 affirme, et le déclarer
négatif serait tirer une conclusion d'un manque de données. Le gate se lit sur
l'artefact de transitions, **avant le premier fit**.

## Grille de décision — GELÉE

Chaque bras est jugé sur **sa propre** nulle du maximum : K = 13, 100 tirages,
permutation intra-instance, jeu de paires recalculé à chaque tirage, lue sur
l'AUC⊥ de sa strate aveugle.

| issue | condition | conséquence |
|---|---|---|
| **T1 — LE TYPE DE DÉPÔT EXPLIQUE** | framework franchit sa barre, bibliothèque non | le succès de w46 est un fait sur les **frameworks**, pas sur JS/TS. Le périmètre servi se redéfinit par type de dépôt |
| **T2 — NI L'UN NI L'AUTRE** | les deux franchissent | ni le langage ni le type n'expliquent : le levier est le volume ou la qualité des données |
| **T3 — RIEN NE SE REPRODUIT** | aucun ne franchit | le résultat `vuejs` n'est reproduit nulle part, sur ~102 instances et deux types de dépôt. Le périmètre servi est **un dépôt**, et la disclosure doit le dire |
| **T0 — NON ÉVALUABLE** | un bras sous le gate de puissance | on ne conclut pas, et on dit lequel et pourquoi |

**Aucune variante nouvelle.** P16 rejoue les **13 variantes gelées de P13**, à
l'identique. Le corpus change, pas la grille — c'est ce qui en fait un test
sévère et non une nouvelle pêche. L'interdiction de quatorzième variante, posée
par P15 et déclenchée par S3, reste en vigueur.

**LORO exigé.** Six dépôts sont attendus au-dessus de la précondition de
lisibilité (≥ 10 instances **et** ≥ 30 paires aveugles portées par le dépôt).
Pour la première fois, le LORO est évaluable des deux côtés ; il est **exigé**
pour toute promotion, et une variante non couverte reste non promue.

## Correctifs de harnais en vigueur, hérités et non négociables

Le rejeu utilise `p12_replay.py` **inchangé**. Il porte les cinq correctifs de
P12 plus les trois du 29-30/08 : attente de transport avec code de sortie 75,
noms de conteneurs assainis, code de sortie lu par l'orchestrateur.

Trois gardes se sont révélés inopérants le 30/08 et leur vérification est
**obligatoire** ici :

1. **codes de sortie** — chaque étape du pipeline lève (`p14_pipeline2.sh`) ;
2. **dénombrement** — la nulle ne démarre que si les 13 variantes existent ;
3. **fils BLAS** — épinglés dans l'**environnement du lancement**, jamais dans un
   initializer de pool ; vérification `nlwp = 1` par worker après démarrage.

## Ce que cette fenêtre ne fait pas

- **Elle ne touche pas au modèle servi.** Le rescopage de la disclosure
  (`vuejs`, 54 paires) est une fenêtre distincte.
- **Elle ne rouvre pas P14.** R3 est acquis.
- **Elle ne promeut pas V11 ni V13.** Leur promotion reste bloquée faute de LORO.
- **Elle n'ouvre pas le bras JS/TS.** Volet 2 du plan, conditionnel à un
  adaptateur Multi-SWE-bench, fenêtre séparée.

## Perte de rejeu — déclarée AVANT la lecture des gates (2026-09-01, 09:40)

Le rejeu rend **117 des 120 instances mesurées, 4 échecs**, tous du côté donnée
et aucun du côté transport. Cause identifiée : la suite de tests de ces instances
dépasse les 900 s d'un appel `sh`. Ce n'est pas un défaut de harnais — l'erreur
`Argument list too long` qui touchait six instances a été corrigée (commande
passée par stdin, contrôlée sur 300 Ko) et a disparu.

**Ventilation de la perte, lue avant tout gate et tout fit :**

| bras | population d'étude prévue | mesurée | perte |
|---|---|---|---|
| framework | 38 | **36** | −2 (`starlette` 1715, 488) |
| bibliothèque | 62 | **61** | −1 (`tox` 1960) |
| témoin de fidélité | 20 | **19** | −1 (`pennylane` 5851) |

**Décision, et son motif.** La campagne continue. La perte est de 3,3 %, et elle
est **conservatrice pour la thèse à démontrer** : le bras framework — celui qui
doit franchir sa barre pour rendre T1 — perd proportionnellement le plus
(−5,3 % contre −1,6 %). Une perte qui pénalise l'hypothèse testée ne peut pas la
fabriquer.

**Ce qui n'est pas modifié** : aucun seuil, aucune règle, aucune grille. Le gate
de puissance se lit sur les **paires aveugles réellement produites**, jamais sur
la projection de 4,7 paires par instance qui a servi à le dimensionner.

**Ce qui est refusé** : relever le timeout pour récupérer les deux `starlette`.
Huit exécutions à plus de quinze minutes dépasseraient de toute façon le plafond
de 7 200 s du processus enfant, et bricoler un plafond après avoir vu quelles
instances il élimine serait de l'ingénierie de seuil.

## Gates P16, et le défaut qu'ils révèlent (2026-09-01, 09:50)

| gate | valeur | verdict |
|---|---|---|
| D1 volume | 1069 paires · 114 instances | **OK** (≥700 · ≥70) |
| D2 fidélité (témoin) | **100,0 %** sur 123 tours | **OK** (≥70 %) |
| D2′ variance | 73,4 % d'instances à issue mixte | **OK** (≥60 %) |
| D3 persist=0 | 73,0 % | **NON** (≥80 %) |
| D4 y=1 | 27,6 % (295 positifs) | reporté, plus un gate |
| D4′ paires aveugles | **2019** | **OK** (≥121) |
| **D5 intégrité** | **78,0 %** | **NON** (≥90 %) |

D2 à **100 %** sur le témoin est le meilleur résultat de fidélité de la campagne
(P14 : 84,4 %). Et 2019 paires aveugles est 2,5× le total de P14, 37× celui de
w46. Mais **D5 échoue**, et sa décomposition est le fait important de cette
lecture.

### D5 n'échoue pas uniformément — il échoue dans un seul bras

| dépôt | bras | tours gardés | tests déclarés non observés |
|---|---|---|---|
| `starlette` | framework | 98,3 % | 0 |
| `tornado` | framework | 97,2 % | 0 |
| `falcon` | framework | 95,8 % | 0 |
| `textual` | framework | 94,6 % | 0 |
| `tox` | biblio | 92,5 % | 0 |
| `pennylane` | biblio | 83,0 % | 27 |
| `streamlink` | biblio | 69,2 % | 3 |
| **`wemake-python-styleguide`** | **biblio** | **6,7 %** | **89** |
| **BRAS framework** | | **95,7 %** | **0** |
| **BRAS bibliothèque** | | **66,7 %** | **119** |

**Le bras qui doit échouer pour rendre T1 est celui dont la mesure est
dégradée.** Un T1 lu tel quel ne distinguerait pas « les bibliothèques ne portent
pas de signal » de « les bibliothèques ont été moins bien mesurées ». C'est
exactement le confondu que cette fenêtre existe pour casser, réintroduit par le
harnais.

### Règle d'intégrité par dépôt — déclarée maintenant, appliquée aux DEUX bras

> **Un dépôt qui retient moins de 50 % de ses tours est exclu comme NON MESURÉ,
> quel que soit son bras.**

Le seuil est fixé sur un principe — la moitié — et non sur la valeur qui
arrangerait : appliqué aux huit dépôts, il n'en retire qu'un, `wemake` à 6,7 %,
et laisse `streamlink` à 69,2 % dedans alors que c'est le suivant. Les 89 tests
déclarés non observés de `wemake` viennent d'un désaccord de format
d'identifiants pytest sur un greffon flake8 : ce ne sont pas des mesures
négatives, ce sont des **absences de mesure**.

Après exclusion :

| bras | tours | gardés |
|---|---|---|
| framework | 324 | **95,7 %** |
| bibliothèque | 400 | **82,3 %** |

L'écart tombe de 29 à 13 points. Il ne disparaît pas.

### Ce que ça impose à la lecture du verdict

1. **D5 reste consigné en ÉCHEC** sur le corpus complet. On ne le recalcule pas
   pour le faire passer.
2. **Le taux de rétention par bras est publié à côté du verdict**, toujours.
3. **Un T1 devra être qualifié** : si le bras framework franchit sa barre et pas
   le bras bibliothèque, l'écart de rétention de 13 points reste une explication
   concurrente non écartée. T1 ne pourra être servi sans une réplication sur des
   dépôts de bibliothèque à rétention comparable.
4. Ce que l'écart **ne peut pas** produire : chaque bras est jugé sur **sa
   propre** nulle, calculée sur **ses** paires. Une nulle par permutation
   s'auto-calibre sur la taille et le bruit du bras. La rétection n'offre donc
   pas un T1 mécanique ; elle offre une explication concurrente, ce qui est
   différent et se dit.

### D3 échoue de nouveau, et pour la même raison qu'en P14

73,0 % contre 80 % exigés (P14 : 63,9 %). Décision identique et pour le même
motif : D3 lit un taux marginal, pas la strate que la métrique consomme, et
cette strate compte ici **2019 paires**. D3 reste consigné en **ÉCHEC**, il n'est
ni amendé ni supersédé, et la question qu'il laisse ouverte reste ouverte.

## Vérification

- **Sélection** : recoupement avec P14 **nul**. Si un dépôt de P14 réapparaît, le
  bras bibliothèque n'est pas indépendant — arrêt.
- **Sélection** : zéro instance d'étude avec `r = 0` ou `r = n` hors témoin.
- **Gates** lus **avant** le fit, puis le gate de puissance.
- **Nulle** : `nlwp = 1` par worker vérifié après lancement.
- **Toutes étapes** : une entrée de ledger, artefacts sha256, aucune écriture
  dans un artefact scellé.
