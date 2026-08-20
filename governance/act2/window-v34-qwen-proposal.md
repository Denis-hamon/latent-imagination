# Fenêtre v34 — boucle cumulée Qwen3.8 rétabli (owner : « conserver Qwen en solveur »)

Qwen3.8 restauré côté endpoint (testé : content non nul, fences propres).
Qwen = meilleur solveur TS mesuré (v32 : 9 convergences, 6 résolutions
exclusives). Il tournait en v32 avec son défaut d'extraction (fences rongées
par le reasoning) ; fenêtre dédiée pour mesurer son vrai niveau avec la
boucle cumulée v32 et une consigne de format renforcée.

## Protocole gelé

- Mécanisme v32/v33 inchangé (état cumulé, prompt code courant réel,
  feedback riche 1600 chars, patch --batch fuzz, vitest TAP) ;
- delta unique : préfixe de consigne « Respond with ONLY the content of the
  ```diff block. No explanations, no reasoning text outside the block. »
  (mitigation fences, figée ici) ;
- population : les MÊMES 17 instances vue (replay-selection-v32.json) ;
- modèle unique : Qwen3.8-2.4T-A95B-NVFP4, ≤4 tours, cap 80 appels.

## Grille scellée

- R1 : resolution rate ≥ 70 % (≥12/17) ;
- R2 : apply rate ≥ 45 % des tours ;
- R3 : budget ≤ 80 appels ;
- descriptif : comparaison avec Qwen v32 (27 % apply, 9 convergences) et
  avec l'union v32+v33 (11/17).
Réussite ⇒ score de référence interne = résultat v34 ; échec ⇒ le KO de v32
était la cause principale et le plafond solveur interne est ~11/17.
