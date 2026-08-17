# Fenêtre v18 — pool TS réel avec axe goal (owner « ok go », suite v17 VALIDÉ)

v17 a montré : cd-only = 0.502 (hasard) sur tickets réels, axe goal = 0.741.
v18 construit le pool qui porte ce résultat : les 430 lignes harvest RÉELLES
(214+/216−, omniroute+zod, golds = diffs fix_commit au parent), embeddings
jina protocole servi, mesures scellées, proposition de promotion (l'architecture
de serving de l'axe goal reste décision owner — hors fenêtre).

## Population figée (export v18-rows.json, sha consigné)

430 lignes : harvest-results*.jsonl cumulés, appliquées, ticket avec
fix_commit, diff sur disque. State/diff bit-identiques au disque ; gold =
`git diff fix~1 fix -- src_files`. Exclusion : date-fns (aucune ligne
appliquée avec gold exportable), synthétique (pas de gold dans les manifests).

## Protocole gelé

- E_state, E_diff, E_goal : embed jina-v2-base-code (protocole ghost_server.embed) ;
- A1 REPRODUCTION (garde d'implémentation) : goal axis sur le sous-ensemble
  v17 (312 lignes, keys identiques) doit redonner 0.7408 ± 0.01 ;
- A2 POPULATION COMPLÈTE : AUC axe goal (loao_energy+report) + IC95 bootstrap 1000 ;
- A3 POISON ext-LOAO (famille entièrement held-out, recette pooled6/7) :
  AUC ≥ 0.65 ET classe min ≥ 5 par famille servie ;
- A4 CONFORMAL (descriptif) : strates Mondrian α=0.10 sur l'axe goal, familles.

## Grille scellée (avant mesure)

A1 ET A2 (AUC pleine population ≥ 0.70, IC95 ≥ 0.65) ET A3 ⇒ pool v18
PROMOUVABLE ; artifact de proposition de promotion produit avec les 4 mesures
+ question serving explicite (qui consomme l'axe goal : assess_patch /
risque : risk_scan reste goal-free par construction — jamais modifié dans
cette fenêtre). Échec ⇒ pas de pool ; les embeddings restent acquis.

## Interdits

Aucune sélection de lignes post-mesure ; aucun mélange dans le pool v18 servi
avant gate ; le pool v12 reste servi tant qu'un gate de promotion owner-signé
n'est pas exécuté ; risk_scan n'est pas modifié.

---

## FERMETURE — 2026-08-17 (grille 3/3, pool PROMOUVABLE)

- **A1 reproduction** : 0.7408 exact (attendu 0.7408 ±0.01) — implémentation fidèle ;
- **A2 population complète** (430 lignes, 139 tickets, 214+/216−) : AUC axe
  goal **0.7495**, IC95 bootstrap 2500 **[0.7019, 0.7969]** (grille ≥0.70 / ≥0.65) ;
- **A3 poison recette pooled6** : PASS (classe min 214 ≥ 5) ; descriptif
  cd-only LOAO-f1 = 0.6008 ;
- **A4 descriptif** (recette conformal simplifiée, quantile — PAS la fonction
  gelée conformal_tau avec Wilson) : strates repo-entières ne tiennent pas la
  garantie (omniroute err réalisée 0.189 > 0.10 ; zod 0.667 sur 6 retenues).
  Lecture : conforme goal exige des strates plus fines (par fichier de test /
  sous-famille) — à dimensionner dans la fenêtre de serving.

Pool sauvegardé : `latent-pool-v18.json/.npz` (E_state/E_diff/E_goal jina,
goal_free=false, 430 lignes). Artifact : window-v18-pool-goal-mesure-2026-08-17.json.

**DÉCISION OWNER REQUISE (hors fenêtre, rien n'est servi)** : qui consomme
l'axe goal ? Candidate naturelle : `assess_patch` (accepte déjà goal_text ;
le chemin cd/cg existe dans le code). `risk_scan` reste goal-free par
construction. Le pool v12 reste servi tel quel.
