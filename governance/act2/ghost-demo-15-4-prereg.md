# Pré-enregistrement — Démo Ghost 15.4 (compare_patches sur v9-replay)

Scellé AVANT toute exécution de la démo. Population d'évaluation connue du
monde (11 diffs v9 groundés en P0), protocole et gates figés ici.

## Population

K = 11 candidats (7 Flash + 4 épinglé) sur 3 triples OmniRoute ; vérité
terrain P0 : 2 positifs (lesquels = ceux labellisés y=1 en P0, révélés
seulement au scoring, pas au design), 9 négatifs. Embeddings 768-d déjà
mesurés en P0 (session-embeds.npz) — ZÉRO appel modèle dans toute la démo.

## Protocole

- Prior scores : LOAO-F1 goal-free contre pool v10 seul (aucune issue locale) ;
- 4 SCÉNARIOS indépendants : seed s ∈ {1,2,3,4} ⇒ sélection bootstrap n=3
  (greedy spread sur prior scores, déterministe par seed) ⇒ 12 exécutions
  réelles de tests Kimsufi (grounded_by: tests-run) ;
- Calibration par scénario : régime fallback-prior (n=3 < N_MIN=8) —
  divulgation obligatoire dans chaque sortie ;
- Prédiction hors-bootstrap : 8 candidats/scénario ⇒ 32 prédictions au total,
  sign(score_goal_free) sur contexte pool∪local ;
- Recommandation top-1 = argmax score.

## Gates pré-enregistrées

- **G1** : sur 4 scénarios, la recommandation top-1 est un VRAI positif dans
  ≥ 3/4 (sinon : le produit ne sait pas recommander — disclose, pas de démo).
- **G2** (intégrité calibration) : 100 % des sorties portent le régime
  correct (fallback-prior avec n=3 < 8 divulgué) et grounded_by = tests-run.
- **G3** (qualité prédictive, descriptive) : accuracy des 32 prédictions
  hors-bootstrap vs vérité terrain P0 ; rapportée avec IC Wilson — aucun
  seuil de go/no-go (mesure d'information, jamais de promesse).

## Interdits

Aucun réglage post-mesure (seed/scoring/régime) ; aucune exclusion de
candidat après coup ; la vérité terrain P0 ne doit PAS influencer la
sélection des n bootstrap (sélection = prior scores seuls).

## Amorce ledger

chaîne : fenêtre v9 e93948f2 ; cette démo réutilise exclusivement des
mesures déjà effectuées (P0) + exécutions de tests réelles.
