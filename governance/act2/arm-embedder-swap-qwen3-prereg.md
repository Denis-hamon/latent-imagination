# Bras ARM — embedder-swap Qwen3-Embedding-8B (OVH AI Endpoints) — pré-enregistrement

Scellé AVANT mesure. Fait suite à l'analyse géométrie-variants (le signal vit
dans E_diff ; l'encodeur lui-même n'avait jamais été challengé) et à la
découverte que unixcoder-base tronque à 512 tokens (état/diff longs invisibles).

## Hypothèse

Un encodeur plus puissant (Qwen3-Embedding-8B, dim 4096, contexte 32 K,
pooling API managé) augmente l'AUC ext-LOAO sur la population certifiable de
référence pooled2 (80 lignes, 51+/12-, AUC unixcoder = 0.6634, IC95
[0.492, 0.830]).

## Protocole gelé

- MÊMES textes que le protocole unixcoder : state = problem[:1200] + "; " +
  f2p[:6] ; diff = contenu diff.patch ; goal = zéro explicite (goal_free) ;
  reconstruits depuis staging-extract + gen-results (jamais ré-écrits).
- API OVH AI Endpoints (base oai.endpoints.kepler.ai.cloud.ovh.net/v1),
  modèle Qwen3-Embedding-8B, batches 16, sans instruction-prefix (comparaison
  contrôlée) ; token jamais loggé ni commité.
- MÊME mesure : s11.norm(E_diff) → LOAO-F1 ext-only (propre tâche exclue) →
  AUC Mann-Whitney + bootstrap CI (2000, seed 20260816).
- Contrôle d'échelle : le score unixcoder 0.6634 est RE-calculé dans le même
  run (même fonction, mêmes npz) pour exclure tout drift d'implémentation.

## Grille de décision (scellée)

- AUC_qwen3 >= 0.65 ET IC95 excluant 0.60 ⇒ bras PROMOUVABLE : plan de
  migration (ré-embedding pool v10, re-calibration conforme v0.6.x, cérémonie)
  soumis à décision owner ;
- AUC_qwen3 < 0.65 OU IC incluant 0.60 ⇒ unixcoder confirmé, bras CLOS ;
- dans tous les cas : rapport publié, aucun mix silencieux d'espaces
  d'embedding (espaces incompatibles entre eux par construction).

## Interdits

Aucun choix de texte/dim/pooling après coup ; aucun ré-essai non journalisé ;
l'espace qwen3 ne rejoint AUCUN pool servi tant qu'une cérémonie de migration
complète (gates 9.1 comprises) n'est pas passée.


## ERRATUM 2026-08-17 (ajouté post-ancrage, avant toute mesure)

La constante « AUC unixcoder = 0.6634 » ci-dessus référençait pooled1
(63 lignes). La population de ce bras est pooled2 (80 lignes), dont le
baseline exact est **0.6739 IC95 [0.5474, 0.7951]**. Le contrôle du run a
reproduit 0.6739 à l'identique avant tout appel API ⇒ aucun drift, erreur de
constante dans le texte. Grille de décision inchangée : >=0.65 ET IC95
excluant 0.60 => PROMOUVABLE, sinon CLOS. Ligne ledger d'amendement ajoutée.

## ADDENDUM 2026-08-17 — re-test jina-v2-base-code sur pooled4 (113 lignes)

Suite DW-41 : pooled4 (80+/33-) atteint AUC unixcoder 0.6951 IC95
[0.595, 0.793] p(<0.60)=0.032. Le bras sweep df5aa51e est RÉ-OUVERT pour un
re-test unique de jina-v2-base-code (meilleure estimation du sweep : +0.049
sur pooled2) avec la MÊME grille scellée : PROMOUVABLE seulement si
AUC >= 0.70 ET IC95 lo > 0.60 ; sinon CLOS définitif (aucun 3e round).
Textes identiques (state=problem[:1200]+f2p, diff=diff.patch) sur les 113
lignes ; contrôle unixcoder recalculé même run. Coût API ~$0.05.
