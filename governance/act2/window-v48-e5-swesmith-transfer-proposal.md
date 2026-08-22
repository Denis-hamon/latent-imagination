# Fenêtre v48 — E5 : transfert cross-langue du modèle de transition sur SWE-smith (Python)

**Demandeur** : menu post-v45, E5 autorisé par l'owner (2026-08-22, « go pour la
mini-campagne façon DW-59 »). **SCÉLLÉE par l'owner le 2026-08-22** (« je scelle
v48 restructurée qu'on attaque en premier ») : grille S1/S1-AGNOSTIQUE/S2/S3
et gate de rendement P1 (<150 transitions → HALT) gelés, aucun seuil ajustable.
Restructuration du 22/08 (question owner sur la géométrie Python) : le Bras B
(refit Python, recette v39/v41 intégrale) est DANS la fenêtre ; P3 agentique
reste conditionnelle à une décision owner séparée.
**Question** : le modèle de transition v41 (entraîné JS/TS, servi v0.8.2)
transfère-t-il zero-shot à des trajectoires Python ? Le périmètre produit est-il
« JS/TS seulement » ou plus large ?

## Finding préalable (vérifié 2026-08-22, reshape la campagne)

1. **RED reproductible** : smoke-test Kimsufi sur `mahmoud__boltons.3bfcfdd0.
   func_pm_ctrl_invert_if__2te3u0dq` — image Docker pullée en 15 s, bug patch
   appliqué, 2/2 F2P échouent (TypeError), run pytest 0,07 s. Harness natif
   SWE-bench-like : `/testbed` + conda env `testbed`, pytest node ids.
2. **Les labels « resolved » de matched-items.json sont INUTILISABLES tels
   quels** : 72,7 % des 5 460 patches résolus ciblent des fichiers sans rapport
   avec le repo de l'instance (pdfminer×oauthlib, glom×charset_normalizer,
   h11×sqlparse, boltons×dask/funcy — le smoke-test l'a prouvé en direct :
   `git apply` échoue, fichier absent). Le « matching » amont a croisé les
   patches. Seuls ~1 407/5 460 passent l'heuristique de cohérence repo↔patch.
3. Conséquence : la vérité-terrain ne peut venir QUE de l'exécution des tests
   (jamais du label). Phase 1 = vérification empirique RED→GREEN par instance,
   zéro LLM. La phase agentique DW-59 (multi-tours) devient Phase 2 optionnelle.

## Population gelée (avant tout pull)

- Source tâches : `swe-smith-tasks/smith-tasks-v1/raw/train-*.parquet`
  (59 136 instances, F2P/P2P non vides, 151 repos, image Docker dédiée chacune).
- Source patches : `swe-smith-trajectories/smith-matched-full/matched-items.json`.
- **Sélection figée** : les ~1 407 instances (résolues ∩ cohérentes
  repo↔patch par l'heuristique de chemins, liste JSON persistée avant
  campagne) — AUCUN autre patch utilisé en Phase 1.
- Hôte : Kimsufi-standard (Docker 28.2.2 x86_64 natif, 372 Go libres).
- Objectif de volume : ≥150 transitions Python vérifiées RED→GREEN (parité
  avec les 180 de v41) ; plafond 400.

## Protocole Phase 1 (zéro LLM, déterministe)

Par image (regroupée par repo, pull unique) :
1. `docker pull` ; container dormant ; pour chaque instance de l'image :
2. worktree propre = `git stash/reset` du /testbed de l'image à son commit
   (les images SWE-smith sont au commit de base SANS le bug) ;
3. appliquer le bug patch (parquet) : `git apply --recount` sinon
   `patch -p1 --fuzz=3` (recette mswb) ; run F2P → **gate RED : TOUS les F2P
   échouent**, sinon instance rejetée ;
4. appliquer le patch candidat (matched, cohérent) ; run F2P + échantillon P2P
   (≤10) → **gate GREEN : tous les F2P passent ET aucun P2P échantillonné ne
   casse**, sinon rejetée ;
5. transition retenue : (red_from=F2P au tour bug, diff=patch candidat,
   red_to=∅ ou résidu mesuré) ; persistée en jsonl format v39-compatible
   (`swe-smith-transitions-python.jsonl`).
Budget infra figé : disque images ≤ 300 Go (pull → vérifier → `docker rmi`
par image terminée si pression) ; timeout pytest 300 s/run (recette mswb) ;
durée campagne bornée à 3 jours de calcul hôte.

## AMENDEMENT P1 approuvé par l'owner (2026-08-22, avant tout run)

**Défaut de conception détecté après scellage** : SWE-smith single-shot ⇒
`resolved=True` ⇒ tous les F2P passent après le fix ⇒ `red_to = ∅` sur toutes
les transitions ⇒ **zéro label positif** ⇒ le Bras B (refit Python) était
infittable tel quel. La recette v39/v41 apprend « quels tests restent rouges
après CE diff » ; sans exemples de tests-qui-restent-rouges, pas de fit.

**Amendement (approuvé : « ok go pour ta reco »)** : P1 génère AUSSI les
transitions d'ablation par hunk — pour chaque instance vérifiée RED→GREEN à
fix multi-hunks, appliquer (fix − hunk_i) et mesurer les F2P qui redeviennent
rouges (vérité = exécution, mécanisme identique à v49/E3, validé d'abord sur
les 33 tickets JS/TS de v49 avant portage Python). Ces transitions à `red_to`
non vide fournissent les positifs du Bras B.

**Ce qui NE change PAS** : grille S1/S1-AGNOSTIQUE/S2/S3, gate de rendement
(<150 transitions → HALT), plafond 400, population source gelée
(`selection-coherente.json`, 1 414 instances), zéro LLM en P1/P2, P3 toujours
conditionnelle à une décision owner séparée. Le décompte du gate porte sur
transitions vérifiées (full-fix) + transitions d'ablation retenues.
**Séquencement acté** : v49 d'abord (validation du mécanisme d'ablation sur
terrain connu), puis v48 avec le harnais éprouvé.

### AMENDEMENT n°2 approuvé par l'owner (2026-08-22) : gold-fix = reverse(bug)

La route des patches « resolved » appariés est MORTE en exécution : sur
l'image pandas (198 instances), 0/46 vérifiées, ~96 % de rejets APPLY_FIX —
les patches solver sont driftés vs la base des images (même `git apply --3way`
fusionne avec conflits), confirmando le finding n°2 (72,7 % mal appariés)
au-delà du prévu. À l'inverse, le `bug_patch` du parquet est la vérité-terrain
(injecté par SWE-smith, toujours applicable) : **son inverse est le gold fix,
prouvé sur instance réelle** (pandas 9obafqet : bug → 100 failed ;
reverse(bug) → 100 passed ; ablation appliquée et mesurée).

Changements : `fix_patch := reverse(bug_patch)` (fonction déterministe
`hunk_split.reverse_patch`, validée involution 20/20 + application git sur
Kimsufi) ; le champ fix_patch de la sélection n'est plus utilisé. Le fallback
`patch --fuzz=3` est SUPPRIMÉ de la chaîne d'application (risque de faux
GREEN sur patches driftés — intégrité des transitions).
**Ce qui NE change PAS** : population gelée (1 414 instances), grilles
S1/S1-AGNOSTIQUE/S2/S3, gate <150 → HALT, plafond 400, zéro LLM, mécanique
d'ablation (amendement n°1).
**Caveat ajouté** : les diffs gold-fix sont des DÉ-MUTATIONS synthétiques
(on défait le bug injecté), pas de vrais fixes d'issue — décalage de domaine
inhérent à SWE-smith, divulgué dans le verdict.

## Phases d'évaluation — reproduire la méthode, pas seulement la tester

**Restructuré le 2026-08-22 (question owner)** : la fenêtre ne s'arrête plus
au zero-shot. Elle reproduit la recette complète v39/v41 sur données Python :
données vérifiées → refit logistique → LOO-trajectoire → isotonic → Youden →
grille contre persistance. La « géométrie Python » (poids + calibration
spécifiques) est produite DANS cette fenêtre.

**Gate de rendement P1 → P2** : si la Phase 1 produit < 150 transitions
vérifiées RED→GREEN, HALT avant tout fit — verdict DATA-INSUFFISANT avec taux
de rejet par gate (la Phase 3 devient alors la condition de poursuite,
décision owner).

### P2 — deux bras + baseline, sur la population Python gelée de P1

- **Bras A (zero-shot)** : modèle v41 GELÉ (poids servis
  `transition-model-served.npz`, encodeur jina-code multilingue inchangé),
  mêmes features `[E_d ‖ E_t ‖ E_d·E_t ‖ persist ‖ frac ‖ turn]`, turn=2.
- **Bras B (refit Python = géométrie spécifique)** : MÊME recette que v39/v41,
  rien d'autre : features identiques (embeddings jina des diffs/tests Python),
  logistique L2 C=50 (convention P0-v46), LOO par trajectoire (clé
  (instance) — une instance SWE-smith = une trajectoire single-shot), isotonic-
  PAV poolée + seuil Youden. Entraîné sur les paires déclarées Python de P1
  uniquement (zéro mélange JS/TS dans ce bras).
- **Baseline** : PERSISTANCE seule `[persist]`, même pipeline, sur la même
  population.
- Métriques identiques v39/v41 : AUC paire + Jaccard sur transitions à red_to
  non vide. Échelle attendue : 150-400 transitions × 1-3 F2P ≈ 600-1200 paires
  — c'est l'échelle EXACTE de la recette originale (v41 : 747 paires / 30
  positifs) ; le volume « très important » n'a jamais été la source de la
  performance JS/TS (c'est la structure séquentielle + la calibration).

### Grille de décision scellée (seuils v39 réutilisés tels quels)

| zone | condition | verdict |
|---|---|---|
| S1 GÉOMÉTRIE PYTHON | Bras B : AUC ≥ persist + 0,03 ET Jaccard ≥ persist + 0,05 | la recette se reproduit en Python ; géométrie Python (poids+calibration) validée ; ouvre la fenêtre produit de serving Python (décision owner, nouvelle fenêtre) |
| S1-AGNOSTIQUE | S1 ET Bras A passe aussi les deux seuils | plus fort : une seule géométrie couvre les deux langues ; le refit Python reste l'actif de référence mais le zero-shot est utilisable |
| S2 PARTIEL | Bras B : une seule des deux métriques passe | signal ambigu ; analyse par sous-population (taille F2P, type de patch, repo) avant conclusion ; pas de serving |
| S3 PAS DE RECETTE | Bras B : aucune des deux | la recette séquentielle ne transfère pas en Python même ré-entraînée ; E5 clos, disclosure périmètre JS/TS confirmée structurellement |

### P3 — volume agentique (CONDITIONNELLE, jamais automatique)

Le single-shot SWE-smith ne donne qu'une transition par instance. Le vrai
volume (trajectoires multi-tours, dizaines de milliers de paires) exige la
boucle agentique DW-59 (solveur LLM ≤4 tours, état cumulé, pose par fichier).
P3 n'est PAS dans le budget scellé de v48 : déclenchement = décision owner
après le verdict P2, avec cap d'appels LLM gelé à l'avance dans une nouvelle
fenêtre (jamais de budget ouvert).

## Interdits / caveats

- Zéro confiance dans les labels `resolved` (finding n°2) : seule l'exécution
  fait foi ; les taux de rejet aux gates RED/GREEN seront reportés.
- Zéro appel LLM en P1 et P2 ; P3 = fenêtre séparée sur décision owner.
- Modèle SERVI v0.8.2 intouché : le bras B est un actif expérimental local,
  jamais un swap de serving (le serving Python éventuel = fenêtre produit).
- Pas de pooling JS/TS+Python dans cette fenêtre (bras B pur Python) — un
  bras pooled serait une v48b avec sa propre grille, pour éviter tout choix
  de représentation après coup.
- Caveat comparabilité Bras A : population Python ≠ distribution
  d'entraînement ; un échec de A ne préjuge pas de B (c'est tout l'objet de
  la restructuration).
- Images x86_64 sur hôte x86_64 : pas d'émulation ; rien à conclure pour un
  autre hôte.

## Coûts

- 0 appel LLM (P1+P2) ; ~100-120 images Docker (pulls bornés, ménage au fil
  de l'eau) ; runs pytest 0,1-300 s ; calcul hôte ≤ 3 jours ; refit Python
  ≤ 30 min CPU local (leçon v47 : ce fit est trivial une fois les embeddings
  faits). Temps humain ~1 semaine.

## Artefacts attendus

- `data/landing/act2-pilot/w48/selection-coherente.json` (liste gelée des ~1 407)
- `scripts/act2/w48_swesmith_verify.py` (pipeline RED→GREEN par image)
- `data/landing/act2-pilot/w48/swe-smith-transitions-python.jsonl`
- `scripts/act2/w48_refit_python.py` (recette v39/v41 appliquée au Python)
- `data/landing/act2-pilot/w48/transition-model-python.npz` (géométrie Bras B)
- `scripts/act2/w48_transfer_eval.py` + `w48/transfer-results.json` (A vs B vs persist)
- verdict : `governance/act2/arm-artifacts/arm-v48-e5-transfer-verdict-<date>.json`
  + entrée `prereg-ledger.jsonl`

## P2 JOUÉ (2026-08-22) — verdict S2 PARTIEL, et pourquoi ce n'est pas une clôture

Verdict scellé (`arm-v48-e5-transfer-verdict-2026-08-22.json`) : Bras B AUC
0,924 (T1 passe) / Jaccard 0,688 (T2 échoue, seuil 0,827) → S2 PARTIEL. Bras A
zero-shot : AUC 0,499 / Jaccard 0,004 = hasard (S1-AGNOSTIQUE mort, périmètre
JS/TS confirmé).

**Le T2 est cassé par construction, pas par le modèle.** Le mécanisme qui
fournit les positifs (single-shot + ablation) force `persist=1` constant sur
les 30 984 paires — la baseline persistance devient un prédicteur constant,
son Jaccard 0,777 est un artefact du déséquilibre de classe (majorité
« encore rouge »), pas une mesure de sa capacité à discriminer. La grille
supposait la variance de persist observée en v39/v41 ; le mécanisme
d'ablation qui donne les positifs Python la détruit par construction. Même
piège que DW-58 (médiane Jaccard aveugle en régime ≥50 % triviales) — deux
occurrences en une nuit, actée comme règle transverse (voir menu post-v45).

**Chiffre honnête retenu, hors grille** : AUC 0,73 sur le sous-ensemble F2P
réduit (cas réaliste), une fois pandas retiré (73 % des paires, AUC 0,990
sur 13 positifs seulement — trop peu pour ne pas être suspect). Ni échec ni
victoire : signal modeste et réel.

### AMENDEMENT n°3 — DÉCIDÉ owner (2026-08-22) : ni clôture, ni P3. Baseline non-dégénérée d'abord.

Décision explicite : **ne pas clore E5** (l'échec du T2 constate un
instrument cassé, pas une preuve que la recette échoue) ; **ne pas ouvrir
P3** (campagne agentique multi-tours, coûteuse) avant d'avoir un instrument
de mesure propre — dépenser plus sur un signal ambigu serait la faute qu'on
a évitée toute la nuit.

**Protocole de l'amendement, dans l'ordre, sans dérogation** :
1. Définir la construction de la baseline non-dégénérée AVANT tout nouveau
   calcul : exclure le sous-ensemble single-shot qui force `persist=1`
   constant, garder uniquement les paires où `persist` a une vraie variance
   (a priori : le sous-ensemble ablation à `red_to` non vide, mais la règle
   d'inclusion doit être écrite et gelée AVANT de regarder si le nombre
   qui en sort est bon).
2. **Sceller le nouveau seuil AVANT de recalculer.** Interdiction explicite
   de réutiliser le 0,884 « ablations seules » déjà observé comme clôture :
   c'est exactement le grid-shopping post-hoc nommé DW-37 — le chiffre a
   déjà été vu, donc toute grille qui le cible après coup est invalide par
   construction, même si le protocole ci-dessus y ressemble. Écrire le
   seuil, l'ancrer dans le ledger, PUIS calculer.
3. P3 reste hors budget de cette fenêtre, sans changement : décision owner
   séparée, après le nouveau verdict, avec cap d'appels LLM gelé à l'avance.

Rien d'autre ne change : population gelée, zéro LLM, actif Bras B non servi.
