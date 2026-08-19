# Fenêtre v31 — re-jugement n°4, grille v23 IDENTIQUE, population désaturée

La population entraînable est désaturée pour la première fois (triviales
42 % < 50 %, 148 non-triviales) grâce aux trajectoires d'agents réels (v30)
complétant les collectes génératives (v22/v25/v28). Re-jugement du modèle
per-test (recette 3896a3e7, λ 1e-2 gelé) sur 429 lignes. Zéro appel LLM.
Grille strictement identique v23 : M1 médiane Jaccard LOO-ligne ≥ B1 + 0.05 ;
M2 AUC paire ≥ 0.62 ; M3 subset sources neuves médiane ≥ B1 + 0.05.
Passage ⇒ poids v4 servis (v0.8.2, backup v3, drill rollback, blackbox
zed-hosted). Échec ⇒ constat définitif sur la médiane, campagne close.
