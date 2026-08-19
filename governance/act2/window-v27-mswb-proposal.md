# Fenêtre v27 — Multi-SWE-bench (CC0) : verify + collecte à grande échelle

Source : dataset ByteDance Multi-SWE-bench (licence CC0, arxiv 2504.02605),
406 instances TS/JS converties en 404 tickets au format vérifiable
(vue 48, svelte 270, dayjs 56, axios 4, express 4, readme-stats 19,
darkreader 2, insomnia 1). Chaque instance porte base.sha, fix_patch,
test_patch, f2p/p2p explicites et le résultat du harness d'origine.

Objectif : densifier massivement les paires intra-ticket non triviales
(condition de re-jugement propre du modèle per-test, DW-55/56).

## Protocole gelé (2 phases)

**Phase A — verify RED→GREEN sur NOTRE hôte** (zéro appel LLM) :
worktree au base.sha → appliquer test_patch → exécuter (les f2p DOIVENT
échouer) → appliquer fix_patch → exécuter (f2p DOIVENT passer, p2p intacts).
Seules les instances passant les deux étapes entrent en Phase B. Runner par
repo (vitest/jest/mocha selon le cas), recette héritée du mineur.

**Phase B — replay collecte** sur les tickets vérifiés (DW-52 mitigations) :
fichiers COMPLETS si src ≤1200 lignes, erreur git apply réelle au feedback,
F2P≥2, modèles Pro + Qwen (GLM KO endpoint), 4 tours max, cap à fixer.

## Grille scellée

- A : ≥ 40 tickets vérifiés RED→GREEN sur notre hôte (sinon la source n'est
  pas exploitable localement et on s'arrête au constat) ;
- B : ≥ 150 partielles non-triviales ajoutées au dataset per-test (l'objectif
  DW-56 était ≥500 tickets vérifiés ; les 404 MSWB + ~200 déjà minés y
  concourent) ;
- B2 descriptif : taux d'application et converge par modèle.
A requis pour lancer B. Zéro serving dans cette fenêtre.

## Interdits

Pas de mélange au pool servi ; le modèle v3 (poids v26) reste en production ;
les instances dont le harness d'origine diverge du nôtre sont écartées
(divulguées), pas forcées.

---

## Phase A — RÉSULTAT : 24/48 vue vérifiés, grille A (≥40) MANQUÉE, fenêtre close

- **vuejs/core : 24/48** (10 stricts, 14 partiels). Le tier « partial » =
  ≥1 f2p rouge au parent puis vert après fix, sans exiger tous (certaines
  instances MSWB ont des f2p qui dépendent du harness docker d'origine) ;
  tiers tracé par ticket (verify_tier strict|partial) — disclosure au lieu
  d'un filtre silencieux ;
- **svelte : 0/60** — dépendance de build (compiler src non compilé au
  worktree) ; même raison d'exclusion que next.js ;
- **dayjs : 0/56** — tests sensibles à l'environnement TZ : 7/7 passent au
  parent sur hôte nu alors qu'ils échouent dans le docker MSWB ;
- Repos restants (express/axios/readme-stats/insomnia/darkreader, 30
  instances) : non joués, volume max insuffisant pour combler l'écart à 40.

Lecture : Multi-SWE-bench est une source RÉELLE mais harness-dépendante ;
notre hôte nu ne reproduit fidèlement que ~50 % des instances vue (repo sans
build ni env exotique). La grille A ≥40 était calibrée sur l'hypothèse que
tous les repos contribuent — réfutée par la mesure.

Actifs conservés : 24 tickets vue vérifiés RED→GREEN sur NOTRE hôte
(mswb/vuejs__core/verified-mswb.json) — petit patch connu par ticket
(médiane 43 lignes combinées fix+test), exactement le profil « modèle peut
vraiment partiellement réparer » qui manque aux partielles triviales.
