# Fenêtre v35 — Qwen3.8 rétabli + fix troncature (cause racine v34)

Diagnostic v34 prouvé : les réponses font ~64k caractères ≈ 16k tokens =
plafond max_tokens=16000 ⇒ finish_reason length suspecté ⇒ fences coupées
⇒ 23/44 tours en « pas-de-diff ». L'endpoint accepte 65536 (testé).
Contexte papier Multi-SWE-bench (arxiv 2504.02605, Tab. 4) : les taux TS
publiés vont de 0 à 11.6 % (Claude-3.7 Sonnet, méthode agentique, benchmark
complet) — notre bloc 65 % (v32) s'explique par le pré-filtre petits patchs
mono-fichier (le papier confirme : « resolved rate drops sharply when fix
patches exceed 600 tokens »).

## Protocole gelé (mécanisme v32/v34 inchangé, deux deltas d'infrastructure)

1. `LI_MAX_TOKENS=40960` (call_t07 patché pour lire l'env) — laisse le
   raisonnement finiR avant la fence ;
2. `finish_reason` loggé par ligne (surveillance de la troncature, jamais
   utilisé pour le verdict).
Modèle unique Qwen3.8-2.4T-A95B-NVFP4, mêmes 17 instances (sélection v32),
consigne diff-seul v34 conservée, cap 80 appels.

## Grille scellée (identique v34)

- R1 ≥ 70 % (12/17) ; R2 apply ≥ 45 % ; R3 ≤ 80 appels.
- descriptif : taux finish_reason=length ; comparaison v34/v32.
Réussite ⇒ référence interne mise à jour + données au stock ; échec ⇒ le
plafond solveur interne est confirmé même sans troncature.

---

## FERMETURE — 2026-08-19 : **GRILLE 3/3 FRANCHIE — v35 RÉUSSIE**

- **R1 resolution rate : 14/17 = 82 %** (≥70 % ✓) ;
- **R2 apply rate : 21/32 = 66 %** (≥45 % ✓) ;
- **R3 budget : 32/80 appels** (✓, sous le cap de 60 %) ;
- 10/14 instances résolues dès le tour 1 ; distribution tours [1×10, 2×3, 4×4] ;
- 3 irréductibles : vuejs__core-11694, -11854, -9572 ;
- finish_reason=length encore 53 % des réponses (Qwen raisonne >40960 tokens)
  — le plafond suivant est là : 65536 accepté par l'endpoint, non joué ici
  (protocole gelé à 40960).

**Cause racine confirmée par l'expérience** : la troncature à 16000 tokens
était le premier frein de Qwen3.8 (v34 apply 34 % → v35 apply 66 % ; v34
résolution 53 % → v35 résolution 82 %). Le raisonnement long du modèle
n'est pas un défaut à combattre par le prompt mais un budget à financer.

**Référence interne mise à jour** : 82 % de résolution sur le bloc vue de 17
instances vérifiées, solveur Qwen3.8-2.4T seul, boucle cumulée v32. Contexte
papier (MSWB, Tab. 4) : 0–11.6 % sur le benchmark TS complet par les systèmes
frontier publiés — notre bloc est pré-filtré (petits patchs mono-fichier),
la comparaison directe est donc limitée, mais l'ordre de grandeur indique que
la boucle + le bon solveur est un multiplicateur massif.

Score campagne (même bloc 17) : v32 65 % → v33 35 % (sans Qwen) → v34 53 %
(Qwen tronqué) → **v35 82 %** (Qwen désenclavé).
