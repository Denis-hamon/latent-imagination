# Fenêtre v36 — Qwen3.8 max_tokens 65536 sur les 3 irréductibles (et re-run bloc)

v35 a franchi la grille (82 %) mais 53 % des réponses Qwen finissent encore
en finish_reason=length à 40960 tokens : le plafond suivant est mécanique.
L'endpoint accepte 65536 (testé v35-prep). Population : les 17 instances du
bloc (les 3 irréductibles en priorité : 11694, 11854, 9572).

## Protocole gelé

Mécanisme v35 inchangé + `LI_MAX_TOKENS=65536`. Qwen seul. Déjà-résolues
en v35 : jouées aussi (nouvelle exécution, la fenêtre est auto-contenue),
arrêt anticipé par instance à convergence. Cap 80 appels.

## Grille scellée

- R1 : ≥ 15/17 résolues (88 %) ;
- R2 : apply ≥ 66 % (niveau v35, le fix 65k ne doit pas dégrader) ;
- R3 : ≤ 80 appels ; descriptif finish_reason=length.
Réussite ⇒ référence interne 88 % + plafond mécanique levé ; sinon référence
v35 confirmée (82 %) et le reste est cognitif, pas budgétaire.

---

## FERMETURE — 2026-08-19 : **GRILLE 3/3 — v36 RÉUSSIE, nouvelle référence interne**

- **R1 : 15/17 résolues = 88 %** (≥88 % ✓, cible exacte atteinte) ;
- **R2 : apply 22/28 = 79 %** (≥66 % ✓) ;
- **R3 : 28 appels** (≤80 ✓, 65 % sous le cap) ;
- finish_reason=length : 7/28 (25 %, contre 53 % à 40960) — le plafond
  mécanique recule mais ne disparaît pas (Qwen raisonne parfois >65k tokens) ;
- 12/15 résolues au tour 1 ; 2 irréductibles : vuejs__core-9572 (5 F2P),
  vuejs__core-11854 (2 F2P — dont 1 f2p fichier, matching partiel) ;
- trajectoire campagne : 65 % (v32) → 35 % (v33 sans Qwen) → 53 % (v34 tronqué)
  → 82 % (v35 40k) → **88 % (v36 65k)**.

Le plafond restant (2/17) est probablement cognitif, plus budgétaire :
les deux instances résistent à 4 tours avec contexte complet.
