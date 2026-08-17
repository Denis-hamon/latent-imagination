# Bras ARM — modèle per-test dédié (pré-enregistrement, post-v15)

Question (DW-47, moitié non explorée) : un modèle APPRENANT (pas du 1-NN
géométrie) peut-il prédire QUELS tests déclarés restent rouges après une
réparation, mieux que la baseline « tout reste rouge » ?

Le levier AST-diff est déjà réfuté (ext-loao-candidate-astdiff-v10 : AUC
binaire 0.5276) — interdit de le rejouer.

## Population (figée)

69 lignes avec declared_f2p : 45 partielles + 24 complètes (red_set vide).
497 paires (patch, test) : 140 rouges / 357 réparés. Dataset
`pert-test-dataset/pert-test-rows.json` figé — aucune collecte nouvelle.

## Protocole gelé

- Espace servi : jina-v2-base-code, protocole exact de `ghost_server.embed`
  (8192 tok, token_type_ids=0, last-token, shims de compat).
- E_diff : déjà calculés (v15 arm) pour les 58 partielles ; E_diff des 24
  complètes calculés à la même recette ; E_test : embedding jina du nom de
  test (texte nu du nom).
- Paire = concat(E_diff[768], E_test[768], cos(E_diff, E_test)) → 1537 dims.
- Modèle : régression logistique L2 torch (pas de tuning d'architecture) ;
  λ ∈ {1e-3, 1e-2, 1e-1, 1, 10} choisi par leave-one-row-out INTERNE au
  train uniquement (AUC paire sur les folds internes), jamais au contact de
  la ligne held-out.
- Éval : LOO par LIGNE entière (les ~7 paires d'une ligne sortent ensemble),
  prédiction = {t déclaré : p(t rouge | ligne) > 0.5}, métrique médiane
  Jaccard(pred, red_set) sur les 45 partielles.
- Baseline B1 inchangée (mediane 0.6667) ; AUC paire LOO rapportée en
  assainissement.

## Grille de décision scellée

- médiane Jaccard(LOO modèle, partielles) > 0.6667 + 0.05 ⇒ VALIDÉ :
  ouvre l'intégration produit (colonne « tests prédits échoués »
  compare_patches v2, avec recalibration propre ensuite).
- sinon ⇒ CLOS : le per-test n'est pas extractible de E_diff/E_test à cette
  échelle ; le levier perception est alors DÉFINITIVEMENT épuisé, et la
  position produit bascule sur l'acceptation du plafond (acc@10 ~0.90
  conforme comme artéfact final).

## Interdits

Aucune feature/sélection post-hoc ; pas de nouvel embedder ; pas de
bootstrap sur la population ; l'AST-diff n'est pas rejoué.
