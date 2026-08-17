# Bras ARM — prédiction per-test Jaccard (pré-enregistrement, v15)

Question : la géométrie E_diff (jina, espace servi) porte-t-elle de
l'information sur QUELS tests restent rouges après une réparation partielle ?

## Population

58 réparations partielles (red_set non vide) : v15-label 7 + harvest-full 19
+ legacy-reconstruit 32. Shortfall disclosé vs cible indicative 150 (doc v15)
— l'arm est mesuré tel quel, sans complétion opportuniste.

## Protocole gelé

- Embeddings E_diff jina-v2-base-code des 58 diffs (espace servi, protocole
  troncation 6000 chars identique pooled6/7) ;
- B1 BASELINE triviale : pred = declared_f2p (« rien n'est réparé ») ;
- B2 VOISIN-1 sans exclusion de tâche (comportement produit réaliste) ;
- B3 VOISIN-1 AVEC exclusion de tâche (généralisation — métrique de grille) ;
- prédiction = red_set du voisin ; similarité = Jaccard(pred, vérité),
  |truth| >= 1 garanti par construction ;
- LOO déterministe, seed non requis (pas de bootstrap sur la sélection).

## Grille de décision scellée

- médiane Jaccard(B3) > médiane Jaccard(B1) + 0.05 ⇒ arm VALIDÉ : ouvre la
  modélisation per-test (colonne « tests prédits échoués » compare_patches v2) ;
- sinon ⇒ CLOS : le red-set n'est pas porté par E_diff voisinage ; la
  supervision per-test existerait comme donnée mais requiert un modèle dédié
  (hors périmètre v15).
- Descriptif rapporté en sus : Jaccard(B2), part de paires même-tâche à
  red_sets identiques (reproductibilité des patterns d'échec).

## Interdits

Aucune sélection de voisin/métrique post-hoc ; les 3 mesures ci-dessus sont
le verdict complet.
