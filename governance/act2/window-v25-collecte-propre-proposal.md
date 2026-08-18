# Fenêtre v25 — collecte voie propre (Pro + Qwen 3.8, mandat owner)

Owner : « fais la voie propre, avec DeepSeek V4 Pro + GLM 5.2 » puis
correction « GLM semble KO, passe sur Qwen 3.8 + DeepSeek V4 Pro »
(kimi K3 et Qwen 3.8 signalés KO côté endpoint au départ — Qwen finalement
vivant, GLM testé : content null permanent, exclu).

Objectif unique : amener les partielles triviales sous 50 % pour que la
médiane Jaccard redevienne discriminante, condition du re-jugement propre
(DW-55, grille v23/v24 identique SANS amendement).

## Exécution

- Sélection figée avant appels : 40 tickets neufs (dédup v22), kimi 17 /
  qwen 16 / epv 7, F2P 2-27, src ≤ 1172 lignes (fichiers complets DW-52) ;
- 232/320 appels consommés ; 77 appliqués (33 %) ; **24 convergences** ;
- Pro : 112 appels → 48 appliqués (43 %) dont 10 convergences ;
- Qwen : 120 appels → 18 appliqués (15 %) dont 14 convergences, mais
  58 pas-de-diff-extrable (fences reasoning tronquées, problème récurrent) ;
- Dataset per-test : 273 lignes / 209 partielles ; recovery declared harvest
  par id→issue→f2p (+9 lignes) ;
- **Triviales 102/209 = 49 % ⇒ désaturation FRANCHIE.**

## Conséquence

Fenêtre v26 = re-jugement du modèle sur grille identique v23 (médiane,
+0.05, AUC ≥ 0.62) sur 273 lignes — aucune métrique changée, la médiane
est simplement redevenue informative par les données.
