# Fenêtre v19 — assess_patch branché sur l'axe goal v18 (owner : « ok pour cet ordre »)

Ordre approuvé : (1) servir l'axe goal via assess_patch maintenant ;
(2) strates fines conformes PLUS TARD, quand le trafic aura densifié.
risk_scan reste goal-free par construction — jamais modifié ici.

## Intégration (additive, zéro appel LLM)

- `LI_GOAL_CALIB` (nouvel env) : calibration {energy_threshold_youden, J,
  pool=v18, encoder=jina}. Présente ⇒ assess_patch lit ce seuil pour l'énergie
  goal ; absente ⇒ comportement legacy BYTE-IDENTIQUE (rollback = unset env).
- Le seuil est le Youden sur l'énergie LOAO `1−<cd,cg>` du pool v18 — formule
  EXACTE de `energy_of` serveur (loao_energy s11) : zéro écart mesure/serving.

## Grille scellée

- S1 : AUC énergie LOAO sur v18 = 0.7495 ± 0.01 (reproduction signe-près) ET
  Youden J ≥ 0.50 ;
- S2 : descriptif réalisé au seuil (acc pleine population, coverage conf) —
  rapporté, hors grille ;
- S3 : tests unités + sans LI_GOAL_CALIB, assess_patch legacy inchangé ;
  risk_scan/compare_patches non touchés (preuve par diff) ;
- S4 : blackbox LIVE sur ticket réel à vérité connue : candidat partiel (y=0)
  ⇒ advice « regenerate » ; diff du fix réel (y=1) ⇒ « ok-ship » (3 lignes min).
S1+S3+S4 requis pour servir ; échec ⇒ pas de LI_GOAL_CALIB, v18 reste fichier.

## Interdits

Pas de conforme inventé (A4 v18 showed strates repo insuffisantes — le
verdict d'énergie sert avec abstention par conf, disclosure explicite) ;
pas de modification du pool v12 ; pas de re-thresholding post-blackbox.

---

## FERMETURE — 2026-08-17 : **ÉCHEC de la grille, rien n'est servi**

- **S1 PARTIEL** : AUC énergie LOAO = 0.7495 (reproduction exacte de v18 ✓),
  mais **Youden J = 0.4409 < 0.50** ⇒ condition de service NON remplie ;
- **S2 descriptif** : acc pleine population 0.721 MAIS acc top-10 % conf =
  **0.558** — pire que la moyenne : la confiance concentre l'erreur, c'est
  l'inverse de ce qu'exige un régime d'abstention ;
- S3/S4 : non joués (la grille exige S1 pour servir — économie de 0 appel
  respectée, aucune intégration serveur déployée, aucun drop-in modifié).
- Calibration calculée et archivée (`goal-calibration-v19.json`,
  `v19-S1S2-mesure.json`) mais **non servie** : LI_GOAL_CALIB jamais posé.

Lecture honnête : l'axe goal CLASSE bien (AUC 0.75, +0.15 vs cd-only sur
tickets réels) mais ne SÉPARE pas assez à seuil unique pour un verdict
binaire fiable — exactement le profil qui a coûté les fenêtres v5→v14 en
binaire. Le pool v18 (430 lignes avec E_goal) reste acquis comme donnée.

**Décision owner requise pour la suite** — trois pistes, aucune jouée sans feu :
(a) axe goal en RANKING comparatif (pas de verdict binaire) : le signal
mesuré sert à ordonner des candidats, comme compare_patches le fait déjà ;
(b) combiner goal + per-test (le modèle dédié 0.83 Jaccard vit sur les mêmes
tickets) — feature conjointe, fenêtre separate à pré-enregistrer ;
(c) stop TS, le plafond est structurel ; servir uniquement la colonne per-test.
