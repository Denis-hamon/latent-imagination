# Fenêtre v24 — re-jugement modèle per-test sur dataset étendu (DW-55 franchi)

DW-55 condition remplie : 70 partielles non-triviales (B1<1.0) sur 147 avec
declared — la médiane Jaccard n'est plus saturée (était 1.0=1.0 à 49/108).
Re-jugement IDENTIQUE au protocole v23 (c4d89d18), sur le dataset étendu
(196 lignes / 156 partielles / ~1200 paires). Zéro appel LLM.

## Grille (identique v23, ré-enregistrée)

- M1 : médiane Jaccard LOO-ligne sur les partielles ≥ médiane B1 + 0.05 ;
- M2 : AUC paire LOO-ligne ≥ 0.62 ;
- M3 : sous-population v22-replay médiane ≥ B1(v22) + 0.05.
λ=1e-2 gelé. LOO par ligne. Recette mot à mot v23.

---

## FERMETURE — 2026-08-18 : NON PROMOUVABLE (grille inchangée, saturation persiste)

- Population : 177 lignes / 126 partielles (v22-replay 114 inclus, queue glm).
- **M1 médiane : 1.0 vs 1.0 → échec structurel persistant** : 77/126 partielles
  triviales (B1=1.0) = 61 % ⇒ toute médiane reste aveugle. La condition
  DW-55 « ≥50 non-triviales » (70 atteintes) dé-sature la moyenne mais pas la
  médiane : le critère de DW-55 était insuffisant (diagnostiqué ici, pas avant).
- **M2 passe** : AUC paire 0.913 ; Youden J 0.766 ; Brier isotonic 0.0987.
- M3 v22 médiane saturée également (88 partielles v22).
- Hors grille : moyenne Jaccard modèle 0.8065 vs B1 0.7745 (+0.032) ;
  subset v22 seul 0.8892 vs 0.8341 (**+0.055**).

Amendement médiane→moyenne EXAMINÉ et REFUSÉ par l'opérateur/agent : le
passage ne tiendrait que sur ~33 lignes motrices, marge 0.005 — trop fragile
pour du serving. Voie propre retenue : collecte v25 (Pro+Qwen, GLM KO
endpoint) pour amener les triviales sous 50 % et re-juger sur la grille
d'origine SANS amendement.

Poids v24 sauvegardés sur nœud, non servis. Modèle v2 toujours en production.
