# Bras ARM — métrique Mondrian-aware (pré-enregistrement)

Question : le plateau AUC globale ~0.69 (pooled7, 585 lignes) est-il un
plafond géométrique réel ou un artefact de la métrique GLOBALE, alors que le
produit (risk_scan/compare_patches) sert PAR STRATE conforme ?

## Protocole gelé (zéro appel modèle)

Sur pooled7 (embeddings jina-v2-base-code, labels groundés) :
1. AUC LOAO-F1 globale (rappel attendu 0.6946 ± 0.001, contrôle) ;
2. AUC LOAO-F1 INTRA-FAMILLE pour chaque famille à >= 12 lignes (voisins
   restreints à la famille, propre tâche exclue) ;
3. AUC STRATIFIÉE = moyenne pondérée par n des AUC intra-familles (familles
   >= 12) ; familles < 12 : rapportées descriptivement, jamais agrégées ;
4. Nombre de strates conformables (n>=12, classes >= 2) projetées si pooled7
   était servi.

## Grille d'interprétation (gelée avant mesure)

- AUC stratifiée >= AUC globale + 0.05 => le plateau global EST en partie un
  artefact de métrique ; levier v15(a) CONFIRMÉ : scoring/tau par famille à
  proposer au serving (bras de migration séparé, cérémonie standard) ;
- sinon => plateau réel de la représentation jina+LOAO-F1 sur ces familles ;
  levier v15(b) encodeur prioritaire ;
- dans tous les cas : rapport publié, aucune modification de serving.
