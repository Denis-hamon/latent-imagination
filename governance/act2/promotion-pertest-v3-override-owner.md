# PROMOTION exécutée — poids per-test v3 (v26), override owner 2026-08-18

Décision owner (« 1 puis on peut toutefois ensuite continuer d'explorer la
partie 2 ») : override de la grille v26 NON PROMOUVABLE, fondé sur l'évidence
accumulée et sur la démonstration que l'instrument (médiane Jaccard) est
structurellement aveugle dans ce régime (>50 % de partielles triviales,
invariant de la collecte agentique démontré sur v23/v24/v26).

## Ce qui est servi

- Ghost **v0.8.1** ; pool v12 inchangé ; colonne per-test = poids v26
  (pert-test-model.npz : w,b, threshold 0.5422, isotonic 148 points, n_train 1601) ;
- backup : pert-test-model-v2-backup.npz (v2, seuil 0.2873) ;
- rollback : `cp pert-test-model-v2-backup.npz pert-test-model.npz && systemctl restart ghost-mcp`.

## Preuves de la cérémonie

- Drill réel : v26→v2 vérifié (seuil 0.2873 live) → v26 restauré (0.5422 live) ;
- Blackbox live (ticket zed-hosted, 5 candidats réels, 4 rouges réels chacun) :
  **Jaccard 0.800 uniforme v26 vs 0.544 v2 isotonic / 0.634 v2 brut** (+0.26) ;
- Chemin binaire non touché (aucune modification energy_of/pool/calibration) ;
- Grilles d'entraînement : AUC paire 0.894-0.913 (LOO-ligne) ; LOAO-tâche
  honnête gelé 0.6424 (disclosure fuite v23 au ledger) ; Youden J 0.72-0.77 ;
  Brier isotonic 0.099-0.116.

## Disclosure intégrale (override = dette de preuve, pas effacement)

La grille scellée v26 a jugé NON PROMOUVABLE. La promotion est une décision
owner en connaissance de cause, pas une validation de grille. Toute mesure
future de la colonne per-test doit rapporter les DEUX régimes (médiane
saturée et lectures non dégénérées). Prochaine étape d'exploration validée
par owner : partie 2 (volume — Multi-SWE-bench et collecte).
