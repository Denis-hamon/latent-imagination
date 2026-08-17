# PROPOSITION fenêtre v15 — supervision per-test (NON ratifiée)

## Motif (issu de la clôture d'arc perception, 54f79ad + cbc6133)

Sous supervision binaire (y = passe/passe-pas), la perception et la métrique
sont au plafond mesuré (0.69-0.75 global ; intra-famille quasi-aléatoire ;
les 4 encodeurs testés hiérarchisés code-spé > généraliste). Le prochain
signal est plus riche : **prédire QUELS tests échouent**, pas seulement si.
Données déjà sur disque : 201/205 run-results conservent les issues nommés
par test ; 41 réparations partielles nommées ; 4 tâches multi-patterns
(lite.triple x3 patterns) => le signal per-test EXISTE, le volume manque.

## Design proposé

1. **Labeler full-outcomes** : extension du label exec pour capturer l'issue
   COMPLET par test (sans troncature) — les anciens run-results restent
   exploitables via tails (201/205).
2. **Collecte ciblée** : 15-20 tâches triples/hard à >=4 F2P (OmniRoute
   prioritaire — familles denses), Flash x 5-6 tirages (ici les multi-tirages
   sont des FEATURES : chaque pattern d'échec partiel = un label distinct ;
   DW-43 ne s'applique pas à cette supervision).
3. **Dataset** : >= 150 lignes partielles (patch, set-de-tests-rouges).
4. **Bras de mesure pré-enregistré** : LOAO prédiction de l'ensemble-rouge
   (Jaccard / précision par test), jamais de label deviné, grille scellée
   avant mesure, promote seulement si > baseline triviale (prédire
   l'ensemble complet des F2P déclarés) avec marge scellée.

## Produit si succès

compare_patches v2 : colonne « tests prédits échoués » par candidat —
l'artefact exact de la vision PR-Simulator (Table Option/Tests prédits/
Risque), grounded et calibré comme le reste.

## Enveloppe estimée

200-300 appels Flash (rendement triples ~0.45 label/appel) + travail
labeler/mesure zéro-appel. Décision owner requise.
