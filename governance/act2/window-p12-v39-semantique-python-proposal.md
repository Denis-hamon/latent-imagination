# Fenêtre P12 — corpus Python en sémantique v39 (un patch complet par tour)

**Statut : SCELLÉE par l'owner le 2026-08-27** (« ok on build dans la sémantique
v39 comme évoqué »). Fenêtre de DONNÉES. **Zéro appel LLM** : les patchs
existent déjà en amont, seule leur exécution est nouvelle.

---

## Question

P9 a mesuré que le régime JS/TS n'est pas celui d'un solveur qui converge, mais
celui d'un solveur **qui a déjà réussi** : 82 des 97 trajectoires de w46 ont
leurs tests déclarés déjà verts au premier tour, position médiane du passage au
vert = 0,00. Sur les trajectoires OpenHands Python, 0 instance sur 119, position
médiane 0,50. D3 et D4 y sont donc structurellement hors d'atteinte.

La cause n'est pas le langage : c'est la **sémantique de tour**. En v39, un tour
est un patch COMPLET régénéré depuis le parent — une tentative entière, qui peut
réussir seule. En P9, un état est une édition PARTIELLE au milieu d'une session
d'agent : rouge par construction tant que la session n'est pas finie.

P12 pose donc la question à sémantique égale : **le régime JS/TS se reproduit-il
en Python quand un tour est, comme en v39, un patch complet ?**

---

## Source, gelée

`nebius/SWE-rebench-openhands-trajectories` — la même qu'en P9, mais exploitée
autrement : le dataset contient **plusieurs trajectoires indépendantes par
instance** (médiane ~10, jusqu'à 34). Le `model_patch` de chacune est un patch
complet, autonome, régénéré depuis le parent. Une suite de ces patchs pour une
même instance EST une trajectoire au sens v39.

Environnements : images Docker de `nebius/SWE-rebench`, appariées par
`instance_id`, `FAIL_TO_PASS` / `PASS_TO_PASS` de la même source.

## Règles de sélection — DÉTERMINISTES, fixées avant toute exécution

Aucune n'a été choisie au vu d'un résultat d'exécution. Elles s'appuient sur des
métadonnées connues d'avance (nombre de trajectoires, nombre de tests déclarés)
et sur la **forme mesurée de w46**, qui sert de gabarit.

1. **Dépôts** : les 3 de la sélection P9 (`tobymao/sqlglot`,
   `python-pillow/Pillow`, `iterative/dvc`). Aucun nouveau choix de dépôt.
2. Instances ayant **≥ 4 trajectoires** et un **taux de résolution ≥ 0,75**.
3. **Toutes** les instances retenues, sans troncature. Couper à 70 en ordre
   lexicographique éliminait la totalité de sqlglot : la troncature aurait été
   un choix de dépôt déguisé.
4. Instances dont le nombre de tests déclarés dépasse le **maximum de w46 (18)**
   **écartées**, jamais tronquées : tronquer déformerait l'instance, l'écarter
   dit qu'elle n'a pas d'analogue dans le corpus de référence. **1 écartée**
   (`iterative__dvc-2254`, 119 déclarés).
5. **Trajectoires** : blocs consécutifs de **4 tours** dans la liste triée par
   `trajectory_id` croissant ; 2 blocs si l'instance a ≥ 8 trajectoires,
   sinon 1. 4 tours = la longueur maximale de w46 ; ≤ 2 trajectoires par
   instance contre 3 au maximum dans w46.
6. Gel dans `night-harvest/py-p12/p12-selection.json`, sha256 dans
   `p12-selection-freeze.json`, **avant la première exécution**.

**Population gelée : 154 instances · 270 trajectoires · 810 paires de tours ·
972 paires test × tour.** sha256 `6a0d20ccaee96f48b843af596be462b5b5931b347a2aa7f5c4e182345f4d401d`.

| | w46 (référence) | P12 |
|---|---|---|
| instances | 70 | 154 |
| trajectoires | 97 | 270 |
| tours par trajectoire | 2 à 4 | 4 |
| paires test × tour | 747 | 972 |
| poids de la plus grosse instance | 6,4 % | **3,7 %** |
| déclarés par instance (max) | 18 | 18 |

## Vérité par exécution

7. Dans l'image Docker de l'instance : `git checkout` du commit de base,
   application du `test_patch`, puis application du `model_patch` du tour.
8. **Contrôle d'intégrité (D5 adapté)** : le patch doit s'appliquer proprement.
   Ici rien n'est reconstruit — le patch est pris tel quel — donc le contrôle
   porte sur l'application, pas sur une égalité d'état. Tout tour dont le patch
   ne s'applique pas rend sa trajectoire **écartée et comptée**.
9. Exécution de `FAIL_TO_PASS ∪ PASS_TO_PASS`, relevé de l'ensemble EXACT des
   tests en échec. Un test déclaré non observé n'est pas un test vert : le tour
   est rejeté (garde de contrôle positif, héritée de P9b).
10. **Contrôle d'instabilité** : double exécution à l'état parent ; tout test
    dont le résultat diffère entre les deux passes rend l'instance écartée et
    comptée.
11. Transitions en convention v39 exacte : paires de tours consécutifs (a,b),
    `red_from` = échecs(a), `red_to` = échecs(b), `declared` = `FAIL_TO_PASS`,
    `diff_to` = patch du tour b tronqué à 8 000.

## Gates de données — vérifiés AVANT tout fit

| gate | seuil | attendu au gel |
|---|---|---|
| **D1** volume | ≥ 700 paires **et** ≥ 70 instances | 972 / 154 ✓ |
| **D2** résolution | ≥ 70 % | taux amont moyen 0,952 |
| **D3** régime | part `persist=0` **≥ 80 %** | inconnu — c'est la question |
| **D4** base rate | `y=1` entre **3 % et 15 %** | inconnu — c'est la question |
| **D5** application | ≥ 90 % des tours s'appliquent proprement | inconnu |

**D3 ou D4 raté ⇒ P10 ne s'ouvre pas**, comme en P9.

## Divulgations figées

- **La sélection FABRIQUE le régime, et c'est délibéré.** Le filtre « taux de
  résolution ≥ 0,75 » est l'équivalent Python du gate D2 de `window-v40` qui a
  produit le corpus JS/TS. P12 n'est donc pas une découverte que « le Python
  atteint le régime » : c'est la démonstration que **la même ingénierie
  appliquée au Python produit le même régime**. Un rapport sur la population
  NON filtrée (mêmes dépôts, ≥ 4 trajectoires, sans seuil de résolution) est
  produit en parallèle pour rendre l'effet du filtre lisible.
- **Solveur amont unique** : Qwen3-Coder-480B-A35B-Instruct via OpenHands
  v0.54.0, pour tous les tours. w46 mêle DeepSeek-V4-Pro et Qwen3.8. La
  comparaison des AUC devra en tenir compte (firewall DW-37).
- **Ordre des tours arbitraire mais déterministe.** Les trajectoires amont sont
  indépendantes : leur ordre par `trajectory_id` n'a pas de sens temporel. w46
  a le même caractère — ses tours alternent vert/rouge/vert, ce ne sont pas des
  itérations convergentes.
- **Recouvrement** : 43 des 154 instances appartiennent aussi à la sélection P9.
  **Zéro recouvrement avec P9b** — le test de transfert P12 → P9b reste propre.
- **Brouillons d'agent retirés du patch appliqué** : `.openhands/**` et les
  fichiers NEUFS de premier niveau (`reproduce_issue.py`…). Même règle qu'en P9,
  même motif : ils polluent `diff_to`, qui est une entrée du modèle, et la
  troncature à 8 000 caractères masquerait alors le vrai correctif.

## Interdits

- Aucun fit, aucune AUC, aucun seuil dans P12. Le fit est P10.
- Aucun élargissement de la sélection après avoir vu les gates.
- Aucun sous-ensemble choisi après résultats.
- Aucun mélange avec `SWE-smith` (DW-37), ni avec les populations P9 / P9b.
- Aucun patch réparé à la main pour qu'il s'applique.
