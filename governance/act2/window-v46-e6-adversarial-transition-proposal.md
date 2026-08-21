# Fenêtre v46 — E6 : sondage adversarial du modèle de transition

**Demandeur** : menu d'expérimentations post-v45 (`menu-experimentations-post-v45.md`,
E6 = « PROCHAINE PRIORITÉ »). Proposition rédigée le 2026-08-21, scellage owner
attendu avant toute construction de cas.
**Question** : le AUC 0,9931 / Jaccard 0,9333 LOO-trajectoire du modèle de
transition v41 (servi v0.8.2) est-il de la vraie lecture sémantique du diff,
ou un raccourci de surface (tokens présents, taille, style) ? C'est la seule
expérience du menu qui attaque DIRECTEMENT le doute initial de l'arc 2.

## Motivation

Le modèle ne lit le diff qu'à travers `Ed = embed(diff[:8000])` (jina
v2-base-code) + son produit scalaire avec l'embedding du nom de test
(`ghost_server.py:predict_transition`, features figées arm-v39 :
`[Ed ‖ Et ‖ Ed·Et ‖ persist ‖ frac ‖ turn]` = 1540 dims). Un lecteur
sémantique doit voir qu'un diff DONT ON INVERSE L'EFFET (lignes +/- échangées)
ne répare plus le test ; un lecteur de surface garde les mêmes tokens et ne
bouge pas. La sonde revert sépare ces deux régimes sans aucun appel LLM et
sans aucune donnée nouvelle.

## Population gelée (avant tout calcul)

- Les **180 transitions** de `data/landing/act2-pilot/transitions/v39-transitions.jsonl`
  (v32→v40, builder figé à la clôture v40 — MÊME population que v41 et v45).
  70 trajectoires, 747 paires (transition, test déclaré), 432 positifs.
- **Vérifié sur les fichiers** : 279 paires `t ∈ red_from \ red_to` candidates
  à la sonde R ; 0 diff dépasse 8000 chars (aucun artefact de troncation
  possible — la troncation servie ne coupe jamais rien sur cette population) ;
  population 100 % JS/TS (vuejs__core 60, kimi-packages 49, qwen 22, dayjs 12,
  epv-tests 15, autres 22).
- Artefact servi copié depuis le nœud (lecture seule) pour contrôle de
  fidélité : `data/landing/act2-pilot/transition-model-served.npz`
  (feat_dims 1540, λ 0.01, seuil Youden 0.0190, isotonic 703 pts, 2026-08-21).

## Protocole gelé

### P0 — Reconstruction persistée du harnais LOO (prérequis, livrable en soi)

Le harnais d'entraînement v39/v41 n'a jamais été persisté (runs inline) —
lacune déjà tracée pour E9. `scripts/act2/w46_transition_refit.py` le
reconstruit à l'identique du protocole arm-v39 + recette servie :
features `predict_transition`, logistique L2 λ=1e-2 (LBFGS), LOO par
TRAJECTOIRE entière, calibration isotonic-PAV sur probas LOO, seuil Youden.
**Contrôle positif obligatoire** : la reconstruction doit reproduire
AUC 0,9931 ± 0,005 et Jaccard 0,9333 ± 0,015 (référence v41 ; la tolérance
Jaccard couvre l'écart de matching documenté v41↔v45, ±0,04 sur la
persistance). Hors tolérance → HALT : diagnostic des conventions
(turn/frac/matching) autorisé en UNE passe tracée, sans toucher à la grille ;
si toujours hors tolérance, la fenêtre s'arrête là (verdict P0-ÉCHEC) — on ne
sonde pas un modèle qu'on ne sait pas reconstruire.
Effet de bord utile : ce harnais débloque E9 (invocations `predict_transition`
en local sans dépendre du nœud).

### P1 — Variantes adversariales, 100 % déterministes (zéro LLM)

Pour chaque transition, à partir de `diff_to` :
- **R (revert)** : inversion de l'effet — lignes `+`↔`-` échangées, en-têtes
  `--- a/`↔`+++ b/` échangés. Même syntaxe, effet sémantique opposé : le
  correctif est défait.
- **N (neutre)** : une ligne `+ // w46-neutral` insérée après le premier
  en-tête de hunk (compteurs du hunk incrémentés). Bruit de surface sans
  effet sémantique — mesure le plancher d'instabilité de l'embedding.
- Cas R éligibles : paires `(transition, t)` avec `t ∈ red_from \ red_to` ET
  prédiction LOO du modèle sur le diff ORIGINAL = vert
  (`p_still_red < seuil`). Le modèle doit d'abord avoir « cru » à la
  réparation pour que la sonde ait du mordant.
- Chaque cas R est évalué avec le pli LOO qui EXCLUT sa propre trajectoire
  (original, R et N avec le même pli) — aucune mémorisation de la population
  d'entraînement dans la mesure.

### P2 — Métriques (toutes prédictées avant lecture des résultats)

- `flip_R` : fraction des cas R où la variante revert est prédite ROUGE
  (le modèle retire sa prédiction « réparé » quand l'effet du diff est inversé).
- `shift_R` : moyenne de `p(revert) − p(original)` sur les cas R.
- `flip_N` : fraction des cas R où la variante neutre change la prédiction
  binaire (plancher de bruit).
- `shift_N` : moyenne de `|p(neutre) − p(original)|`.
- `D = shift_R − shift_N` : discrimination nette du bruit d'embedding.
- Contrôle secondaire (disclosure, hors grille) : même sonde avec `Ed`
  mis à zéro — doit s'effondrer vers le comportement persistance ; si ce
  contrôle ne bouge pas, la sonde elle-même est vide.

## Grille de décision scellée (avant construction des cas)

Justifications a priori des seuils : un lecteur sémantique doit inverser sa
prédiction sur la majorité des 279 cas propres (marge pour tests flaky et
hunks multiples) → 0,60 ; un commentaire neutre ne peut mover qu'une
embedding jitter → 0,10 ; p est calibrée (isotonic), une vraie lecture du
revert doit remonter p nettement au-dessus du seuil → D ≥ 0,20.

| zone | condition | verdict |
|---|---|---|
| A1 ROBUSTE | `flip_R ≥ 0,60` ET `flip_N ≤ 0,10` ET `D ≥ 0,20` | le modèle lit l'effet sémantique du diff ; le 0,9931 est corroboré comme compréhension, pas comme raccourci ; colonne servie maintenue sans changement |
| A2 FRAGILE | `flip_R ≥ 0,35` ET `flip_N ≤ 0,25` ET `D ≥ 0,10` (sans A1) | sensibilité sémantique partielle ; disclosure sur la colonne servie + extension v46b sur trajectoires NEUVES (sweep v44) avant toute extension de confiance |
| A3 EFFONDRÉ | tout le reste (`flip_R < 0,35` OU `flip_N > 0,25` OU `D < 0,10`) | le signal mesuré ne résiste pas à l'inversion d'effet à surface quasi identique ; le 0,9931 ne s'interprète PAS comme « compréhension » ; revue de serving à ouvrir (au minimum disclosure, au pire démotion — décision owner) |

## Interdits / caveats

- Aucun seuil ajusté après construction des cas ; la grille ci-dessus est
  scellée telle quelle au moment de l'ancrage.
- Zéro appel LLM pour construire les variantes (le test perdrait son sens :
  c'est la géométrie du modèle qu'on sonde, pas la capacité d'un LLM à
  générer des contre-exemples).
- Vérité-terrain du revert = PAR CONSTRUCTION : le diff est le seul changement
  appliqué entre t et t+1, donc défaire le diff ne peut pas réparer t. Risque
  résiduel : test flaky entre les deux runs (non détectable ici) — disclosure
  systématique du taux de cas R non inversés malgré diff unihunk (les plus
  propres).
- La sonde porte sur la population d'ENTRAÎNEMENT (atténué par LOO) : A1 ne
  prouve pas la généralisation hors-distribution, seulement l'absence de
  raccourci de surface sur le domaine servi. Les trajectoires neuves (v44)
  restent le test de généralisation — et c'est justement l'objet de v46b si A2.
- Serving v0.8.2 intouché pendant toute la fenêtre ; pas de pooling des
  résultats de sonde dans un ré-entraînement sans nouvelle fenêtre.

## Coûts

- 0 appel LLM, 0 grounding nouveau, ~540 embeddings jina sur CPU local
  (venv `scripts/mcp/venv`, modèle jina déjà en cache HF) + 70 fits LOO.
  Calcul < 1 h. Temps humain estimé : 2 jours (P0 inclus).

## Décision owner (scellée 2026-08-22, avant toute construction de cas)

- **Grille A1/A2/A3 : scellée TELLE QUELLE**, sans ajustement de seuil.
  Aucune modification de `flip_R`/`flip_N`/`D` n'est plus permise à partir
  de cet horodatage — construire P1/P2 et mesurer.
- **E9 : AUTORISÉ, à la suite de P0.** Une fois `w46_transition_refit.py`
  validé par le contrôle positif (AUC 0,9931 ± 0,005 / Jaccard 0,9333 ± 0,015),
  réutiliser cette même instance locale du harnais pour invoquer
  `predict_transition()` sur les 180 transitions et persister la prédiction
  Ghost par transition (jamais fait jusqu'ici — seulement calculée en mémoire
  lors des runs LOO). Coût marginal nul (même harnais, pas de nouvel appel
  LLM, pas de dépendance au nœud GPU). Objectif E9 inchangé : croiser ces
  prédictions × `judge-outputs-*.jsonl` pour la carte d'erreur « juge a
  raison, Ghost a tort » (menu post-v45, seuil de clôture ≥5 cas, cf. DW-16).
  E9 reste une mesure séparée de v46 — ne pas pooler ses résultats dans le
  verdict A1/A2/A3.

## Artefacts attendus

- `scripts/act2/w46_transition_refit.py` (harnais persisté — réutilisable E9)
- `scripts/act2/w46_adversarial_probe.py`
- `data/landing/act2-pilot/w46/probe-cases.json` (cas gelés avant mesure)
- `data/landing/act2-pilot/w46/probe-results.json`
- verdict horodaté : `governance/act2/arm-artifacts/arm-v46-e6-adversarial-verdict-<date>.json`
  + entrée `prereg-ledger.jsonl` ancrée (mêmes cérémonie/OTS que v45).
