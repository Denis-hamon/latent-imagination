# Fenêtre v23 — (b)-bis : modèle per-test ré-entraîné sur 138 partiels réels (owner « ok go »)

DW-54 : v22 a doublé la population d'entraînement du modèle dédié (58 → 138
réparations partielles nommées, 4 sources, multi-repos). Le modèle servi
(arm 3896a3e7 + isotonic 47273883) n'a jamais vu les 80 lignes v22.
Fenêtre de MODÉLISATION : zéro appel LLM, données déjà sur disque.

## Population (figée au dataset builder)

174 lignes / 138 partielles : v15-label 7, harvest-full 19, p2-legacy 32,
v22-replay 80. Paires = (ligne, test déclaré) ; les lignes sans declared_f2p
participent au LOO comme contexte d'entraînement seulement si declared
récupérable, sinon exclues (règle identique arm 3896a3e7).

## Protocole gelé (hérité 3896a3e7 + précision v23)

- features [E_diff(768)‖E_test(768)‖cos] jina protocole servi ; diff tronqué
  8000 chars, nom de test nu ; logistique L2 torch LBFGS 150 ;
- λ FIXÉ à 1e-2 (pas de re-tuning : la sélection LOO interne de l'arm
  3896a3e7 a choisi 1e-2 dans 85 % des folds ; disclosure au lieu du coût
  calcul ×5) ;
- LOO par LIGNE entière (toutes ses paires sortent ensemble).

## Grille scellée

- **M1** : médiane Jaccard LOO sur les 138 partielles ≥ médiane B1 (declared
  complet) + 0.05 — la règle même qui a validé l'arm d'origine ;
- **M2** : AUC paire LOO ≥ 0.62 (seuil G1 v16 conservé) ;
- **M3** (généralisation neuve) : sur les 80 lignes v22-replay SEULES
  (multi-repos réelles, jamais vues par le modèle servi) : médiane Jaccard
  LOO ≥ B1_med(v22) + 0.05 ;
- M1 ET M2 ⇒ poids v3 PROMOUVABLES au serving (pert-test-model.npz v3,
  backup v2 gardé, version Ghost 0.8.1, blackbox comparatif zed-hosted) ;
  M3 rapporté comme diagnostic de généralisation (n'entre pas dans la
  promotion, mais M1+M2 sans M3 ⇒ deployment différé, disclosure).

## Interdits

Pas de feature nouvelle ; pas de sélection de sous-population ; le modèle
v2 reste servi tant que la grille n'est pas franchie puis le déploiement
exécuté.

---

## FERMETURE — 2026-08-18 : NON PROMOUVABLE (grille), verdict de métrique

- Population entraînable : 155 lignes / 1066 paires (507 rouges) — 19 harvest
  déclarés mais 10 diffs non résolus exclus (disclosure).
- **M1 médiane Jaccard : 1.0000 vs 1.0000 → ÉCHEC mécanique** : 59/108
  partielles sont des lignes « rien de réparé » (B1 trivial = 1.0) apportées
  par v22 ; toute médiane est aveugle quand > 50 % de la population sature
  la borne. La métrique gelée n'est pas adaptée à la nouvelle population.
- **M2 AUC paire LOO : 0.9117 ✓** (modèle servi v2 : 0.842).
- M3 idem M1 (saturation).
- Hors grille : moyenne Jaccard 0.7977 vs 0.7526 (+0.045) ; sous-population
  v22 : 0.8941 vs 0.8158 (**+0.078**) ; Youden J 0.7629 (v2 : 0.610) ;
  Brier isotonic 0.1008 (v2 : 0.1035) ; λ=1e-2 gelé ; 34 battues / 56 égalités.

Poids v23 sur le nœud (v23-weights.npz), **non servis**. Le modèle v2 reste
en production. Lecture honnête : progrès réel sur tous les signaux non
dégénérés, mais aucune grille franchie ⇒ pas de promotion.

Décision owner requise : override explicite (servir v23 avec disclosure),
ou conserver v2 et attendre plus de données réelles (queue v22 glm en cours,
stock minage 199 tickets + ~700 candidats). Amendement de métrique
(moyenne au lieu de médiane, marge +0.05 identique) rejoué = v23-bis, mais
les nombres actuels (+0.045 global) n'y passeraient pas non plus.
