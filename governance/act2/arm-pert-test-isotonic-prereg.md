# Bras ARM — recalibration isotonique per-test (pré-enregistrement DW-48 polish)

Question : les probas `p_failing` brutes (sigmoid, seuil 0.5 non calibré)
peuvent-elles être recalibrées sans fuite ni dégradation du classement ?

## Protocole gelé

- Entrée UNIQUE : les 446 scores LOO `loo-scores.json` (par construction
  hors-échantillon : chaque paire scorée par un modèle qui n'a jamais vu sa
  ligne). Aucun nouveau fit sur données vues.
- Régression isotonique PAV (numpy implémenté main, 10 blocs max par pooling
  monotone), fit sur (score_loo, y). La sortie = table de calibration stockée
  dans le npz servi, appliquée APRÈS la sigmoid du modèle.
- Le seuil de décision `predicted_red` reste le Youden 0.2808 sur la proba
  recalibrée correspondante (recalculé sur la même grille de scores LOO
  recalibrés — jamais sur du train).

## Grille scellée

- I1 : Brier LOO recalibré ≤ 0.1071 (brut, mesuré fenêtre v16) ;
- I2 : ECE 10-bins recalibré ≤ ECE brut ;
- I3 : chemin binaire serveUR inchangé (energy_of/calibration v12 intouchés —
  preuve par diff + rerun G3 implicite : aucun code du régime servi modifié) ;
- I4 : blackbox live : la colonne retourne les probas recalibrées et le cas
  zed-hosted reste mesuré (status measured, abstention intacte).
Les 4 requises pour servir la table ; sinon rollback = sigmoid brute (v16).

## Interdits

Pas de nouveau fit de poids ; pas de sélection de blocs post-hoc ;
l'isotonic est le seul recalibrateur autorisé ici (Platt/temperature hors
périmètre — une seule décision).
