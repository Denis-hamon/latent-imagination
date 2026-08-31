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

## Vérification

- **Sélection** : recoupement avec P14 **nul**. Si un dépôt de P14 réapparaît, le
  bras bibliothèque n'est pas indépendant — arrêt.
- **Sélection** : zéro instance d'étude avec `r = 0` ou `r = n` hors témoin.
- **Gates** lus **avant** le fit, puis le gate de puissance.
- **Nulle** : `nlwp = 1` par worker vérifié après lancement.
- **Toutes étapes** : une entrée de ledger, artefacts sha256, aucune écriture
  dans un artefact scellé.
