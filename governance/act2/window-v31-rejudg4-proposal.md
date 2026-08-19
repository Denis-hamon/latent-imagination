# Fenêtre v31 — re-jugement n°4, grille v23 IDENTIQUE, population désaturée

La population entraînable est désaturée pour la première fois (triviales
42 % < 50 %, 148 non-triviales) grâce aux trajectoires d'agents réels (v30)
complétant les collectes génératives (v22/v25/v28). Re-jugement du modèle
per-test (recette 3896a3e7, λ 1e-2 gelé) sur 429 lignes. Zéro appel LLM.
Grille strictement identique v23 : M1 médiane Jaccard LOO-ligne ≥ B1 + 0.05 ;
M2 AUC paire ≥ 0.62 ; M3 subset sources neuves médiane ≥ B1 + 0.05.
Passage ⇒ poids v4 servis (v0.8.2, backup v3, drill rollback, blackbox
zed-hosted). Échec ⇒ constat définitif sur la médiane, campagne close.

---

## FERMETURE — 2026-08-19 : NON PROMOUVABLE (5e tour), CAMPAGNE CLOSE

- M1 médiane : 1.0 = 1.0 sur 203 partielles entraînables (108 triviales =
  53 % : la désaturation dataset 42 % ne se transfère pas à la population
  LOO, les lignes red∩declared=∅ exclues re-biaisent) ;
- M2 AUC 0.8799 ✓ ; M3 saturée ; Youden J 0.672 ; Brier isotonic 0.1257 ;
- décomposition par source (moyenne Jaccard modèle vs B1) :
  harvest +0.060, v22 +0.011, v25 +0.026, legacy −0.075, v15 −0.179,
  **v28 −0.342, v30 −0.419**.

**Leçon finale** : le modèle pooled apprend les TAUX DE BASE par source
(agents SWE-bench vue convergent 75 % ⇒ il prédit tout vert sur les
partielles v30, J 0.08) au lieu de la réparabilité par test — hétérogénéité
des régimes de collecte = barrière de transfert que le volume n'a pas résolue
(1905 paires). La médiane, elle, est prouvée cinq fois aveugle sur cinq
populations distinctes (108→203 partielles, 4 sources, 2 paradigmes).

Décision conforme au prereg : NON PROMOUVABLE,weights v31 non servis,
campagne de modélisation per-test CLOSE. Ghost v0.8.1 (poids v3, époque v26)
reste la configuration servie — elle est née du régime omniroute/zod et y
reste mesurée la meilleure (blackbox live J 0.80). Aucun 6e re-jugement :
la répétition est désormais un coût sans information nouvelle.
