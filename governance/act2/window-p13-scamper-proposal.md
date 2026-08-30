# Fenêtre P13 — SCAMPER sur la représentation : le diff porte-t-il le signal en Python ?

**Demandeur** : suite directe de l'erratum du 2026-08-29 et du verdict P10.
Proposition rédigée le 2026-08-29 — **scellage owner attendu avant le premier
fit de variante**. Zéro appel LLM, zéro Docker, zéro réseau pour les vagues 1 et
3 ; vague 2 en encodage local uniquement.

**Question** : *le plongement d'un patch distingue-t-il, pour un même ticket et un
même test, une tentative qui laisse le test rouge d'une tentative qui le répare ?*
En JS/TS la réponse mesurée est oui. En Python elle est à la nulle. Cette fenêtre
cherche la **représentation** qui la rendrait positive, ou établit qu'il n'y en a
pas dans l'espace exploré.

## Le diagnostic qui motive la fenêtre (mesuré le 2026-08-29, artefacts en cache)

`persist` sépare déjà à 0,91 les paires INTRA où les deux tests n'ont pas le même
statut au tour *a*. La géométrie ne peut donc rien prouver là. Sur la strate où
`persist` est **aveugle** (même statut des deux côtés, baseline 0,5000 par
construction) :

| bras | w46 aveugle (n=54) | P12 aveugle (n=121) |
|---|---|---|
| Ed (diff) | **0,8704** | 0,5372 |
| Et (nom du test) | 0,6296 | 0,5455 |
| complet (1540 d) | 0,8333 | **0,4793** |
| nulle par permutation intra-instance | — | 0,5372 |

Sous-strate « même test, tours différents » — seul le patch change, c'est le cas
d'usage `compare_patches`, et elle porte **105 des 121 paires** de P12 :

| bras | w46 (n=20) | P12 (n=105) |
|---|---|---|
| Ed | **0,7500** | 0,5619 |
| complet | **0,8000** | 0,4952 |
| nulle | — | 0,5333 |

Trois faits gelés qui fixent le périmètre :

1. **La concaténation 1540 d est destructrice en Python** : 0,4793 < 0,5372 (Ed
   seul) et 0,4952 < 0,5619. Sous la nulle. Régime 1540 d / 922 lignes / 69
   positifs / `C=50` — suspect de capacité, à trancher, pas à supposer.
2. **Les métadonnées du diff sont mortes**, mesuré sur les DEUX corpus : stem du
   fichier de test ∩ fichiers touchés, même répertoire, nombre de fichiers,
   taille du diff, « touche un fichier de test » — toutes entre 0,44 et 0,53 sur
   la strate aveugle. **Cet axe est fermé par mesure**, il ne figure pas dans les
   variantes.
3. **P12 est mieux doté que w46 sur la question du produit** : 121 paires
   aveugles contre 54, 105 « compare_patches » contre 20, 31 instances
   contributrices contre 8.

## Métriques gelées

Implémentées et auto-testées dans `scripts/act2/p13_metrics.py` :

- **AUC⊥** *(primaire)* — AUC INTRA restreinte aux paires où
  `persist(a) == persist(b)`. Contrôle de construction : l'AUC⊥ de `persist`
  lui-même vaut exactement 0,5000 (vérifié sur les deux corpus).
- **AUC⊥⊥** *(secondaire, reportée systématiquement)* — sous-strate « même test,
  tours différents ».
- **AUC informative** et **AUC INTRA globale** — reportées pour continuité avec
  l'erratum, jamais utilisées pour décider.
- **IC95 bootstrappés par INSTANCE**, jamais par paire (correctif n°4 de
  l'erratum du 2026-08-29).
- Le pair-set est **recalculé à chaque permutation** : la strate aveugle dépend
  des labels et bouge avec eux.

## Liste des variantes — GELÉE, K = 13

Toute variante hors de cette liste est irrecevable et exige une nouvelle fenêtre.
Le balayage de `C` n'est **pas** une famille de variantes : `C` est un
hyperparamètre **choisi dans le pli** par validation croisée interne groupée par
instance. Un balayage lu à l'extérieur du pli serait K = 9 de plus et un choix
sur les labels d'évaluation.

**Vague 1 — capacité** (embeddings en cache, zéro ré-encodage)

| id | variante |
|---|---|
| `V1` | complet 1540 d, `C` choisi dans le pli |
| `V2` | Ed + scalaires, `C` choisi dans le pli |
| `V3` | Et + scalaires, `C` choisi dans le pli |
| `V4` | PCA(Ed) ⊕ PCA(Et) ajustées **dans le pli**, dimension choisie dans le pli ∈ {16, 32, 64}, + cos + scalaires |
| `V5` | fusion tardive : 2ᵉ étage à 6 d sur `(z_Ed, z_Et, cos, persist, frac, turn)`, LOO imbriqué |
| `V6` | `V1` privé de `frac` et `turn` |

**Vague 2 — canal par test** (ré-encodage local)

| id | variante |
|---|---|
| `V7` | scalaires + cos global + agrégats de cos test↔**hunk** (max, moyenne, top-3, nb de hunks), via `hunk_split.py` |
| `V8` | Et remplacé par le plongement des **lignes ajoutées du `test_patch`** concernant ce test |
| `V9` | Ed remplacé par le plongement du **diff AST-normalisé** (`ast_norm_diff.py`) |
| `V10` | `V9` ⊕ `V8` |

**Vague 3 — objectif et population**

| id | variante |
|---|---|
| `V11` | logistique **conditionnelle** sur les différences de features dans l'instance (Bradley-Terry) — l'objectif appris devient celui qui est mesuré |
| `V12` | fit **stratifié** par `persist` (0 : 33 positifs / 857 ; 1 : 36 / 65) |
| `V13` | fit conjoint **w46 + P12** avec indicatrice de corpus — **sous divulgation DW-37** |

**Écartés explicitement, et pourquoi** : une indicatrice de dépôt est constante
dans une instance, donc structurellement sans effet sur une métrique intra —
elle n'est pas une variante ; le leave-one-repo-out reste un **mode de
validation** appliqué à toutes. Le jackknife par instance est un **contrôle de
robustesse**, pas une variante.

## Nulle du MAXIMUM — protocole gelé

Treize variantes sur 121 paires dont les labels ont été vus. La barre n'est donc
ni 0,50 ni la nulle d'une variante isolée.

1. **Barre exacte** : 200 permutations intra-instance ; à chaque permutation, les
   13 variantes sont refittées en LOO complet et l'on retient le **maximum** de
   leurs AUC⊥. La barre est le **95ᵉ centile de cette distribution**.
2. **Barre intérimaire, conservatrice**, pour lire une vague avant que les 13
   soient implémentées : quantile `1 − 0,05/13` de la nulle d'une variante
   isolée (Bonferroni). Elle ignore la corrélation entre variantes, donc elle est
   **plus haute** que la barre exacte — la lire tôt ne peut pas fabriquer un
   gagnant. Toute lecture intérimaire est étiquetée comme telle.
3. **Puissance déclarée AVANT l'exploration** (correctif n°5 de l'erratum) : la
   vague 0 publie la barre effective et le temps de fit par variante. Si la barre
   exacte dépasse 0,75, la fenêtre est déclarée sous-dimensionnée **avant** de
   lire le moindre résultat, et la vague 4 (élargissement de P12) devient un
   préalable au lieu d'une suite.

## Grille de décision — GELÉE

| issue | condition | conséquence |
|---|---|---|
| **G1 GAGNANT** | AUC⊥ > barre du max **ET** ≥ 0,65 absolu **ET** leave-one-repo-out ≥ 0,60 sur chacun des 3 dépôts retirés | axe établi en Python. Ouvre la vague 4 et une décision de service |
| **G2 PISTE** | franchit la barre du max, échoue le LORO ou le seuil absolu | **piste, pas résultat**. Déclenche la vague 4 pour trancher. Rien de servi, rien de promu |
| **G3 NUL** | sinon | la représentation actuelle du diff ne porte pas le signal en Python. Publié comme fait négatif |

Aucun seuil n'est ajustable après le premier fit. Sous G3 comme sous G1 le
résultat est publiable : il porte sur la représentation, mesuré contre une nulle
correcte, sur le corpus le mieux doté dont on dispose pour la question.

## Hors périmètre de cette fenêtre

- **Le modèle servi n'est pas touché.** `transition-model-served.npz` et la
  disclosure de `predict_transition` restent en l'état jusqu'à décision owner.
- **P11 n'est pas rouvert** (généralisation SWE-smith, fenêtre distincte).
- **P12 n'est pas élargi** hors de la vague 4, conditionnelle à G1 ou G2.
- **Aucune comparaison d'AUC w46 ↔ P12 sans divulgation** (firewall DW-37) ;
  `V13` est la seule variante qui mélange les deux populations et elle porte la
  divulgation dans son artefact.

## Artefacts

- `scripts/act2/p13_metrics.py` — métriques, permutation, bootstrap (auto-testé)
- `scripts/act2/p13_variants.py` — banc : une variante = une fonction rendant `X`
- `data/landing/act2-pilot/night-harvest/py-p12/p13/p13-<id>.json` — un par variante, sha256
- `data/landing/act2-pilot/night-harvest/py-p13/nulle-du-max.json` — la barre
