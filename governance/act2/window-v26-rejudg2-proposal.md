# Fenêtre v26 — re-jugement per-test n°2, grille v23 IDENTIQUE (DW-55 voie propre)

Condition de re-jugement remplie par les données (v25) : triviales 49 % <
50 %, la médiane Jaccard est redevenue informative. Re-jugement du modèle
per-test (recette 3896a3e7, λ 1e-2 gelé) sur le dataset complet 273 lignes /
209 partielles / ~1400 paires. Zéro appel LLM.

## Grille (inchangée — aucune métrique, aucun seuil, aucune population
## dérivée ; seule la taille de la population a bougé, par collecte scellée)

- M1 : médiane Jaccard LOO-ligne partielles ≥ médiane B1 + 0.05 ;
- M2 : AUC paire LOO-ligne ≥ 0.62 ;
- M3 : médiane v22+v25-replay seules ≥ B1(sous-ensemble) + 0.05.
M1 ET M2 requis ; M3 diagnostic de généralisation neuve.

## Issue si validé

Poids v3 servis : pert-test-model.npz v3 (backup v2 conservé, rollback =
re-drop-in), Ghost v0.8.1, blackbox live comparatif sur cas réel connu,
gate 9.1 rerun (chemin binaire inchangé par construction).

---

## FERMETURE — 2026-08-18 : NON PROMOUVABLE (3e tour identique), décision owner requise

- Population finale : 273 lignes / 1601 paires (récupération complète des
  diffs : 6+13 rounds) ; 187 partielles entraînables.
- **M1 médiane 1.0 vs 1.0 ❌** (>50 % des partielles entraînables triviales) ;
  M2 AUC 0.8941 ✓ ; M3 médiane saturée ❌ ; Youden J 0.7165 ; Brier isotonic
  0.1155 ; frac battues 29.9 %.
- Constat établi sur trois re-jugements consécutifs (v23/v24/v26) : la grille
  médiane est structurellement insatisfiable dans le régime de collecte
  agentique (>50 % de partielles « rien réparé »). Ce n'est pas un effet de
  volume — le dataset a doublé trois fois, la médiane n'a jamais bougé.
- Lectures non dégénérées, toutes en faveur du modèle ré-entraîné : AUC paire
  0.84→0.89-0.91 ; Youden J 0.61→0.72-0.77 ; Brier isotonic 0.1035→0.099-0.116 ;
  moyenne Jaccard +0.055 vs baseline sur les données réelles neuves (v22+v25).
- Poids v26 sur nœud (v26-weights.npz), non servis. Modèle v2 en production.

DÉCISION OWNER PENDANTE : (1) override → servir v26 avec disclosure intégrale
(backup v2, rollback documenté) ; (2) statu quo v2 + bascule vers le volume
(Multi-SWE-bench) ou vers le produit.
