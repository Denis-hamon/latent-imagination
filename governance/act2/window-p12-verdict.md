# Verdict P12 — le régime v39 se reproduit en Python

**Fenêtre** : `window-p12-v39-semantique-python-proposal.md`, scellée par l'owner
le 2026-08-27 (ledger 182). **Zéro appel LLM.** Vérité par exécution.

**Données gelées** :

| artefact | sha256 |
|---|---|
| sélection (154 instances) | `6a0d20ccaee96f48b843af596be462b5b5931b347a2aa7f5c4e182345f4d401d` |
| rejeu (154 fichiers, 1 080 tours) | `bc4fce758045d9055a70d9ec7348a76534dd9fe60d8415900b542a5b66b4aa82` |

---

## Question posée

> Le régime JS/TS se reproduit-il en Python quand un tour est, comme en v39, un
> patch complet ?

**Réponse : oui.** Les cinq gates passent.

---

## Les gates

| gate | seuil | **P12** | w46 (référence JS/TS) | P9 (mêmes dépôts, sémantique OpenHands) |
|---|---|---|---|---|
| D1 volume | ≥ 700 paires · ≥ 70 instances | **922 · 154** ✓ | 747 · 70 | 815 · 119 ✓ |
| D2 résolution | ≥ 70 % | **92,9 %** ✓ | — | 60,0 % ✗ |
| D3 `persist=0` | ≥ 80 % | **93,0 %** ✓ | 95,0 % | 35,5 % ✗ |
| D4 `y=1` | 3–15 % | **7,5 %** (69 positifs) ✓ | 4,0 % (30) | 53,0 % ✗ |
| D5 intégrité | ≥ 90 % | **96,3 %** ✓ | — | 26,7 % strict / 98,3 % périmètre |

**Accord avec l'étiquette amont** : 97,6 % tour à tour (92,9 % mesuré contre
95,3 % étiqueté). C'est le contrôle positif du harnais : la mesure retrouve le
verdict que le producteur des données déclare, y compris **sur quel tour** tombe
chaque rouge.

**Forme de trajectoire** — le cœur de la question :

| | w46 | **P12** | P9 |
|---|---|---|---|
| tests déclarés déjà verts au tour 1 | 82/97 (84,5 %) | **253/268 (94,4 %)** | 0/119 (0 %) |
| position médiane du 1er tour vert | 0,00 | **0,00** | 0,50 |
| déclarés rouges à TOUS les tours | non mesuré | **5/268 (1,9 %)** | 46/119 (38,7 %) |

## Ce que ça tranche

L'écart d'AUC 0,97 (JS/TS) contre 0,55 (Python) mesuré jusqu'ici n'est **pas un
écart de langage**. C'est un écart de **tâche**.

`persist=0 ≥ 80 %` n'est pas un critère de qualité de données : il encode une
tâche précise — *prédire une régression sur un test déjà vert*. Un corpus de
trajectoires de réparation part rouge par construction et ne peut pas le
satisfaire, quelle que soit la langue. À sémantique de tour égale, le Python
entre dans le régime JS/TS sans traitement particulier.

---

## Réserves, à porter dans toute lecture de P10

### 1. Le D4 global masque deux dépôts hors couloir, en sens opposés

| dépôt | paires | instances | `persist=0` | `y=1` |
|---|---|---|---|---|
| iterative/dvc | 213 | 28 | 82,6 % | **18,3 %** — au-dessus du plafond de 15 % |
| python-pillow/Pillow | 327 | 49 | 96,9 % | **2,4 %** — sous le plancher de 3 % |
| tobymao/sqlglot | 382 | 75 | 95,3 % | 5,8 % |

Le gate porte sur le corpus, pas sur chaque dépôt : il passe légitimement. Mais
aucun dépôt ne s'installe au milieu du couloir, et le 7,5 % agrégé est une
moyenne entre deux régimes distincts. Un fit qui ignorerait le dépôt
apprendrait en partie à le reconnaître.

### 2. La classe positive est concentrée

69 positifs sur 31 instances distinctes, mais **`iterative__dvc-5839` en apporte
18 à lui seul, soit 26 %**. C'est exactement ce que P10 doit apprendre à
prédire. Une LOO par instance est obligatoire ; une LOO par trajectoire
surestimerait.

Pour mémoire, w46 était plus concentré encore (30 positifs sur 8 instances), ce
qui ne l'excuse pas : c'est une limite commune aux deux corpus.

### 3. Le filtre de sélection fabrique le régime — divulgué, et mesuré

| population des 3 dépôts | instances | trajectoires | résolution amont |
|---|---|---|---|
| toutes | 469 | 4 852 | 41,1 % |
| ≥ 4 trajectoires | 463 | 4 834 | 40,9 % |
| **+ taux ≥ 0,75 → retenu** | **155** | **1 692** | **95,2 %** |

La distribution est bimodale : **209 instances sur 463 sont à 0 % de
résolution**, 155 à ≥ 75 %, 99 entre les deux. Le filtre ne rogne pas une queue,
il prend un mode et laisse l'autre. C'est l'équivalent Python du gate D2 qui a
produit w46 — et sqlglot est le plus filtré (76 retenues sur 273, taux moyen
34,7 %).

P12 ne montre donc pas que « le Python atteint le régime ». Il montre que **la
même ingénierie de sélection, appliquée au Python, produit le même régime**.

### 4. Concentration du corpus

Instance la plus lourde : **3,9 %** des paires (w46 : 6,4 %). Sur ce point P12
est meilleur que sa référence.

---

## Ce qui a été mesuré et écarté

1 080 tours exécutés, **1 040 retenus (96,3 %)** :

| motif d'écart | tours |
|---|---|
| le patch ne s'applique pas (conflit réel avec le `test_patch`) | 36 |
| contrôle inverse en échec | 3 |
| test déclaré non observé | 1 |

**Contrôle de stabilité** : double passe au parent sur chacune des 154
instances, dans deux conteneurs neufs. **Zéro parent instable.**

---

## Cinq défauts de harnais corrigés en route

Tous de la même famille — une opération qui échoue en rendant `exit 0`. Aucun
n'était visible sans contrôle positif ; chacun aurait fabriqué un régime
plausible.

| # | défaut | effet s'il n'avait pas été vu | ledger |
|---|---|---|---|
| 1 | `model_patch` amont sans saut de ligne final (100 %) | `git apply` échoue, le tour est déclaré appliqué et ROUGE — majorité du corpus faussement rouge | 183 |
| 2 | contrôle de conformité par égalité de TEXTE de diff | 119 tours sur 380 rejetés à tort ; `issue.md` — l'énoncé du ticket, livré non suivi dans les images dvc — entrait dans le diff par `git add -A -N` | 184 |
| 3 | identifiants de test tronqués par l'amont (découpage sur les espaces) | un seul id invalide annule toute la campagne pytest → 5 instances Pillow perdues en silence | 185 |
| 4 | `FAIL_TO_PASS` passé en tête à pytest | le test déclaré s'exécutait sur interpréteur froid → rouges fabriqués, gonfle `y=1`, diminue `persist=0` | 186 |
| 5 | `docker pull` redirigé vers `/dev/null` | quota Docker Hub (100/heure) refusé en silence → 87 instances hors corpus, dont **la totalité de sqlglot** | 187 |

Chaque correctif porte son contrôle positif :

- **#1** — `dvc-1262` passe de 2/8 à 8/8 verts, en accord avec l'amont.
- **#2** — conteneur témoin `dvc-2353` : `git apply -R --check` rend `REVERSE_OK`
  là où l'égalité de texte disait « non conforme ». Reprise : 21 → 128 tours
  appliqués sur les 19 instances touchées.
- **#3** — `Pillow-6811` : 104 tests conservés, 1 réparé, 0 écarté.
- **#4** — `Pillow-6917` mesure `[0,1,1,1,1,1,1,1]` tour par tour, identique à
  l'étiquette amont **y compris sur quel tour tombe l'unique rouge** ; avant
  correctif, désaccord sur les huit.
- **#5** — 154/154 instances, zéro échec de tirage.

L'ampleur du défaut #4 a été mesurée et non supposée : le rejeu invalide archivé
(`p12-replay-ordre-f2p-first-20260827-2017/`) et le rejeu final se recouvrent sur
608 tours appliqués des deux côtés. **601 sur 608 (98,8 %) ont un ensemble de
rouges identique** ; les 7 divergences portent toutes sur `Pillow-6917`.

---

## Le verdict P9 a été ré-éprouvé

Le défaut #4 poussait les chiffres **vers** le passage des gates : le verdict P9
(ledger 181) ne pouvait donc pas être réaffirmé sans mesure. Échantillon de 18
instances sur 120, 6 par dépôt en ordre lexicographique — déterministe, aucun
tirage aléatoire à rejouer. Mesures d'origine archivées, instances rejouées sous
l'ordre de collecte.

| | paires | tours | `persist=0` | `y=1` |
|---|---|---|---|---|
| ordre F2P d'abord | 165 | 88 | 50,9 % | 40,6 % |
| ordre de collecte | 165 | 88 | 50,9 % | 40,6 % |

**88 tours comparables, ensemble des rouges identique sur 88/88.** Zéro
divergence. L'effet mesuré sur P12 (1,2 %) était confiné à `Pillow-6917`, un test
dépendant d'une initialisation globale — classe absente de l'échantillon P9.

Limite honnête : 18 instances sur 120, l'invariance n'est pas démontrée sur les
102 autres. Mais renverser P9 demanderait 44,5 points sur D3 et 38 sur D4, soit
que l'ordre décide de la moitié des tours ; le mesuré est 0,0 % ici et 1,2 % sur
P12. **P9 reste fermé** (ledger 189).

---

## Suite

- **P10 (fit) peut ouvrir.** LOO par instance obligatoire. Le dépôt doit être une
  variable contrôlée, pas une entrée.
- **Firewall DW-37** : P12 est une population distincte de w46, de P9 et de P9b.
  Aucune comparaison d'AUC sans divulgation. Solveur amont unique
  (Qwen3-Coder-480B via OpenHands v0.54.0) contre le mélange DeepSeek-V4-Pro /
  Qwen3.8 de w46.
- **Zéro recouvrement avec P9b** : le test de transfert P12 → P9b reste propre.
  43 des 154 instances appartiennent aussi à la sélection P9.
