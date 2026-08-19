# Fenêtre v30 — trajectoires Multi-SWE-bench : patchs d'agents réels mesurés (owner : paradigme 1)

Changement de paradigme acté owner : au lieu de générer des candidats avec
nos modèles API (v22-v28, apply 28-33 %, production lente), on mesure les
patchs PRODUITS PAR DES AGENTS RÉELS (12 modèles × 3 frameworks, sessions
complètes publiées CC0 dans Multi-SWE-bench_trajs). Diversité de qualité
garantie (Claude 3.5/3.7, GPT-4o, o1, o3, R1, V3, Qwen-72B, Gemini…),
zéro appel LLM : uniquement de l'exécution sur notre hôte.

## Population (figée à l'extraction)

- Soumissions finales des trajectoires TS (MSWE-agent : `info.submission` ;
  MagentLess : patch par instance ; OpenHands : hors périmètre v30 —
  extraction depuis historique d'éditions, différée) ;
- restreinte aux instances vérifiables sur notre hôte : vuejs__core
  (24 instances vérifiées RED→GREEN en v27) ;
- dédup par sha256 du texte de patch ( mêmes patches entre modèles possibles).

## Protocole gelé (hérite v27, recette inchangée)

Worktree au base.sha + test_patch appliqué (pose git --recount/fuzz=3),
patch agent appliqué (idem), exécution vitest TAP, parse vitan avec
normalisation des préfixes TAP (bug v28 corrigé en amont), f2p depuis le
dataset MSWB. y = tous f2p verts ET aucun p2p cassé.

## Grille scellée (fenêtre de DONNÉES)

- V1 : ≥ 150 patchs d'agents mesurés sur les 24 instances vue ;
- V2 : ≥ 50 partielles NON triviales (y=0 et ≥1 f2p réparé) ajoutées au
  dataset per-test — le test de l'hypothèse : les agents compétents
  produisent-ils plus de réparations partielles que nos modèles one-shot ?
- V3 descriptif : distribution des classes (convergence / partiel / échec
  complet / inapplicable) par famille de modèles.
V1 ET V2 ⇒ ouvre v31 (re-jugement du modèle per-test, grille v23 identique,
jamais amendée) ; sinon close au constat.

## Interdits

Pas de modification des patchs d'agents tels que soumis ; pas d'entraînement
dans cette fenêtre ; serving inchangé (v0.8.1/v3).

---

## FERMETURE — 2026-08-19 : grille V1/V2 manquée AU SENS STRICT, constat transformant

- 186 patchs d'agents extraits (trajectoires Multi-SWE-bench CC0 : MSWE-agent
  11 modèles + MagentLess, soumissions `info.submission`) sur 48 instances vue,
  restreints aux 24 instances vérifiées sur notre hôte ;
- **126 appliqués (68 %) / 186 — vs 28-33 % pour nos propres générations
  (v22-v28) : les soumissions d'agents SWE-bench appliquent massivement** ;
- y=1 : **94 convergences** (75 %) ; partielles non-triviales : 30 (24 %) ;
  triviales : **2 seulement (1,6 %)**.
- Grille scellée : V1 (≥150 appliqués) manquée à 126 ; V2 (≥50 NT) manquée à 30.
  Fermée au constat conformément au prereg.
- **MAIS distribution inédite** : nos collectes génératives produisaient ~60 %
  de triviales ; les trajectoires d'agents réels n'en produisent que 1,6 %.
  Le dataset passe à 429 lignes / 257 partielles, **triviales 42 %** — première
  désaturation franche de la population entraînable (et non plus du seul
  dataset global comme en v28).

Actifs : v30-pairs.json (126 lignes labellisées agents réels), agent-measured.json,
extract.py + sélection. Le paradigme 1 livre exactement ce qu'il promettait :
de la donnée non-triviale de qualité, sans un seul appel LLM.
