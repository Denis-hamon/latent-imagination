# Fenêtre v40 — densification des trajectoires (owner : « densifier d'abord »)

L'arm v39 (transition séquentielle, VALIDÉ AUC 0.96) repose sur 72 transitions
/ 152 paires : population trop petite pour servir. Densification par la
recette prouvée (Qwen3.8 65k + pensée courte + état cumulé) appliquée au
stock miné jamais rejoué avec cette recette : les ~119 tickets vérifiés
(kimi 129, qwen 46, epv 20, tanquery 3 MINUS les 80 joués en v22/v25 sous
l'ancienne recette tronquée), filtrés src ≤ 1200 lignes (DW-52).

## Protocole gelé

- Mécanisme = v38 (état cumulé, prompt code courant réel, consigne
  raisonnement court, extraction tolérante, raw saving, pose fichier
  anti-corruption heredoc) — aucune invention nouvelle ;
- modèles : Qwen3.8 (recette primaire) + DeepSeek-V4-Pro (diversité de
  transitions : Pro applique à 92 % et converge peu = beaucoup de tours
  intermédiaires labelisés) ;
- sélection figée avant appels : tickets vérifiés non encore joués par la
  recette 65k, F2P ≥ 2, src total ≤ 1200 ; ≤4 tours ; cap 400 appels (200/modèle).

## Grille scellée (fenêtre de DONNÉES)

- D1 : ≥ 150 transitions neuves ajoutées à l'inventaire v39 (l'inventaire
  passe de 72 à ≥ 222) ;
- D2 : resolution rate ≥ 70 % sur la population sélectionnée (la recette
  tient hors MSWB) ;
- D3 : budget ≤ 400 appels.
D1 ET D2 ⇒ ouvre v41 (re-jugement de l'arm transition sur population
densifiée, grille T1/T2 identique) ; sinon constat et décision owner.

## Interdits

Aucun serving ; pas de re-jeu des tickets v22/v25 (leurs lignes anciennes
restent dans l'inventaire telles quelles — hétérogénéité de recette tracée
par fenêtre dans les transitions).
