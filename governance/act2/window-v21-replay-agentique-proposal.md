# Fenêtre v21 — replay agentique multi-tours sur tickets réels (owner « go »)

Objectif : densifier les **paires intra-ticket réelles** (bottleneck identifié
DW-50/51) en exécutant des boucles agentiques avec les 4 modèles API :
générer → poser → tester réellement → feedback → re-générer. Chaque état
intermédiaire est mesuré et labellisé (tour 1 échoué ≠ tour 3 partiel ≠ fix).

## Population (figée à la sélection, avant tout appel)

25 tickets réels vérifiés (fix_commit sur disque), F2P ≥ 4, triés par F2P
desc, exclus les tickets déjà tirés ≥ 6 fois (fraîcheur populationnelle).
Repos omniroute prioritaire, complément zod si disponible.

## Protocole gelé (leçons DW-35, v15, rct_wm_fork)

- Max **4 tours** par (ticket, modèle) ; arrêt anticipé si y=1 (convergé) ;
- chaque tour régénère un diff COMPLET depuis le parent (pas d'accumulation —
  candidats indépendants, labels propres) ;
- feedback au tour t+1 : diff précédent tronqué 3000 chars + sorties de tests
  échoués tronquées 800 chars, template gelé ;
- pose du diff : git --recount puis patch -l --fuzz=3, vérif par sha ;
  restauration worktree en finally ; timeout 240 s par run de tests (DW-35) ;
- mesure = recette harvest v15 patchée (f2p_red, p2p_failed, failed_all,
  passed_all, y) ;
- compteur dédié `call-counter-v21.jsonl`, cap total 480 (4 modèles × 25
  tickets × ≤4 tours = 400 max + marge infra) ; caps par modèle 120.

## Modèles

DeepSeek-V4-Flash (volume), DeepSeek-V4-Pro (convergence attendue), GLM-5.2-NVFP4
(partiels propres), Qwen3.8-2.4T-A95B-NVFP4 (usine à négatifs dont les tours
2-4 = les partiels rares).

## Livraison (fenêtre de DONNÉES, pas d'arm)

- `replay-rows-v21.jsonl` : {ticket, model, turn, diff sur disque, y,
  failed_all, passed_all} pour chaque état posé ;
- rapport de paires : candidats/ticket, paires intra-ticket (y opposés),
  taux de convergence par modèle ;
- RIEN de servi dans cette fenêtre. La reprise (b) modélisation s'ouvre
  SEULEMENT si le volume scellé est atteint : ≥ 1500 candidats mesurés ET
  ≥ 300 paires intra-ticket à y opposés (pré-déclaré ici).

## Interdits

Pas de sélection de tickets post-appels ; pas de réutilisation des négatifs
en one-shot (le but est la boucle) ; aucun mélange avec pool v12/v18 avant
fenêtre de promotion dédiée.

---

## FERMETURE — 2026-08-17 : grille manquée, fenêtre close (fenêtre de DONNÉES)

- Budget : 227/480 appels (chaînes complètes ; shortfall non consommé disclosé).
- 20 tickets × 4 modèles × ≤4 tours : 227 états, **50 appliqués** (22 %),
  1 seul ticket mixte (y opposés) — grille ≥300 paires LOIN d'être atteinte ;
  grille ≥1500 candidats idem.
- Taux d'application par modèle : Flash 12/77 (16 %), Pro 27/77 (35 %),
  GLM 1/8, Qwen3.8 11/60 dont **30 pas-de-diff-extrable** (clôture de fences
  tronquée par le reasoning sur longs prompts).
- **Mesure utile** : Qwen3.8 converge 5 fois en boucle alors qu'il faisait
  0/24 en one-shot (v13) — la boucle agentique transforme les négatifs
  one-shot en candidats, c'est confirmé. Flash/Pro/G : 1 convergence chacun.
- Cause racine = DW-52 : hallucination de contexte sur fichiers longs
  (troncation tête+queue du prompt). Mitigations figées dans DW-52 ; elles
  structurent la prochaine fenêtre de collecte (v22) sur les NOUVEAUX repos
  à fichiers petits (kimi/epv/tanquery/qkf) : le minage GitHub en cours a
  déjà ~990 candidats et 100+ tickets vérifiés kimi.
- RIEN n'est servi ; les 50 états appliqués (labels réels) sont conservés
  dans replay-rows-v21.jsonl + diffs replay-v21/ (réutilisables comme lignes
  de collecte si mixés dans une future fenêtre dédiée).
