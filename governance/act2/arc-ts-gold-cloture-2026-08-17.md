# ARC CLOS — exploration TS/goal (v5→v20), décision owner (c) 2026-08-17

## Verdict d'arc

Le plafond TS est **structurel sous les signaux explorés**, et le seul signal
intra-ticket ayant survécu à la réfutation est la colonne per-test (servie
v0.8.0). L'exploration active est close ; l'accumulation passive (flywheel,
~12 lignes réelles/nuit) continue et reste la seule route vers plus de
paires intra-ticket.

## Chronologie scellée

| fenêtre/bras | résultat | ce que ça a établi |
|---|---|---|
| v5–v14 (TS synthétique + réels) | plateau AUC 0.69–0.75 globale | plus de données ne bougent pas le plafond binaire |
| v15 per-test 1-NN | CLOS (B3 = 0.0000) | la géométrie seule ne généralise pas le red-set hors-tâche |
| v15-bis modèle dédié | VALIDÉ (Jaccard LOO 0.8333) | apprendre la paire (E_diff × E_test) marche intra-tâche |
| v16 DW-48 prod | livrée v0.8.0 (+isotonic 47273883) | colonne probas par test servie, ECE 0.0205 |
| v17 axe goal | VALIDÉ (0.502→0.7408) | le gold réel porte un signal global ; cd-only = hasard sur réels |
| v18 pool goal | PROMOUVABLE (0.7495 IC[0.70,0.80]) | pool v18 acquis (430 lignes réelles, non servi) |
| v19 assess seuil unique | ÉCHEC (J 0.44 ; top-10 % conf acc 0.558) | le signal classe mais ne sépare pas |
| v20 goal ranking | ÉCHEC R1 (paire intra-ticket 0.4198) | l'AUC 0.75 était inter-tickets ; le produit vit intra-ticket |

## Leçon gravée (s'applique à toute future fenêtre)

Toute métrique d'arm doit mesurer le **cas d'usage produit exact**
(intra-ticket pour compare_patches ; verdict binaire calibré pour
risk_scan), jamais la statistique globale facile. Les paires inter-tickets
sont des leurres : elles montent l'AUC sans rien promettre au produit.

## Actifs conservés (données, pas serving)

- `latent-pool-v18` (430 lignes réelles omniroute+zod avec E_goal, AUC 0.7495) ;
- dataset per-test (pert-test-dataset, 82 lignes / 446 paires) + modèle dédié + isotonic ;
- 264 tickets vérifiés avec fix_commit (mine réutilisable si l'accumulation
  produit un jour assez de paires intra-ticket pour retenter goal+per-test).

## Ce qui reste servi (inchangé)

Ghost v0.8.0 : pool v12 (430 lignes, jina, conformal-mondrian 7 strates),
risk_scan goal-free, compare_patches phase 1/2/fully-measured + colonne
per-test recalibrée. Aucun artefact v17–v20 n'est servi.
