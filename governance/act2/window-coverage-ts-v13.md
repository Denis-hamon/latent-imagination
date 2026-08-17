# Window COVERAGE-TS-v13 — Diversité inter-repos : zod + date-fns (pré-enregistrement v1)

Status: APPROVED 2026-08-17 — ratification owner (« il faut enrichir une
nouvelle campagne » + « fais le travail avec DeepSeek V4, Qwen 3.8 et GLM,
mais pas Claude/Codex »). Auteurs harvest : DeepSeek-V4-Flash (principal),
GLM-5.2-NVFP4, Qwen3.8-2.4T-A95B-NVFP4 (sonde d'extractabilité préalable —
incompatible avéré sur prompts longs en v10, à retester sur tickets réels).
Claude Code et Codex EXCLUS du harvest (réservés vitrine agents).

## Diagnostic chiffré (pourquoi cette fenêtre)

pooled5 = 219 lignes certifiables, AUC jina 0.7217 [0.652, 0.788].
Composition : **OmniRoute 77 % (106 tickets réels + 63 mutants)** ; zod 5
lignes (2 %) ; date-fns 3 lignes (1 %) ; reliquats v1-v3 (26 %).
Trajectoire : pooled2 0.7230 -> pooled4 0.7428 -> pooled5 0.7217 — l'ajout
massif de lignes OmniRoute N'A PAS monté l'estimation ponctuelle, elle a
resserré l'IC. Lecture : la géométrie LOAO-F1 sature sur une monoculture
(lignes quasi-dupliquées d'un même repo se ressemblent dans l'espace latent) ;
le signal manquant est la DIVERSITÉ de distribution de code, pas le volume
intra-repo. Cible : **+10 % relatif => AUC >= 0.79 avec IC95 lo > 0.72**.

## Hypothèse mesurée

Les deux sources MIT validées mécaniquement (public-zod-ts @5e608851 runner
vitest prouvé 94 tests ; public-date-fns-ts @a0a39220 runner prouvé) ont des
histoires git riches en vrais fixes (comme OmniRoute — le protocole
ticket-réel SWE-bench-style de la nuit s'y transpose). En densifiant zod et
date-fns à >= 80 lignes chacun avec classes équilibrées, pooled6 doit soit
franchir 0.79 (l'espace jina généralise entre repos — objectif), soit révéler
que le signal est repo-spécifique (découverte également actionnable :
stratification par repo au lieu du mix global).

## Plan de collecte (3 axes, ordre de rendement attendu)

1. **AXE 1 — tickets réels zod** (mineur généralisé) : discovery sur
   packages/zod/src/v4/**/tests/*.test.ts, commit-ajout = candidat fix,
   filtres de surface (<=3 fichiers src, diff <= 300 lignes, prompt <= 2200
   lignes), contrôle RED->GREEN vitest (F2P >= 1, P2P >= 2). Flash x4
   tirages/ticket.
2. **AXE 2 — tickets réels date-fns** : même mécanique, tests par fonction
   (pkgs/core/src/*/test.ts) => familles fines naturelles (date_fns__<fn>).
3. **AXE 3 — triples synthétiques zod/date-fns** (seconde chance négatifs) :
   réutiliser les designs validés v7 (zod triple_minmax_bag 8 F2P ; bizdays
   triple existait) + 2-3 nouveaux triples date-fns terminaison-sûre ;
   tirages Flash + épinglé-si-rétabli sinon GLM.
4. (Repli, seulement si axes 1-2 < 60 tickets validés) : relax contrôlée des
   filtres OmniRoute (diff <= 600, <= 5 fichiers, P2P >= 1 avec disclosure
   veto-affaibli par ligne).

## Enveloppe proposée [NON encore ratifiée]

- **900 appels max** (rendement nuit : ~1 label / 3.2 tentatives ; objectif
  +180-220 lignes => ~600-700 tentatives + sondes + marge) ; sous-caps :
  Flash 700, GLM 200 ;
- pause-infra >= 8 erreurs consécutives ; abort batch no-diff > 65 %
  (ajusté vs 60 % : taux Flash observé 67 % sur tickets durs, disclosure) ;
- quarantaine <= 10 % par batch.

## Mesures (scellées, identiques nuit-harvest)

- Par batch : poison ext-LOAO + AUC/IC bootstrap (seed 20260816) sur
  pooled6-intérimaire (jina) ;
- Par repo : taux de négatifs, familles >= 5/classe (DW-37 : chaque repo
  mesuré seul avant agrégation) ;
- Finale : pooled6 complet ; grille MIX-READY v14 : AUC >= 0.79 OU
  (AUC >= 0.75 ET IC lo > 0.72) ; rapport par-repo ; si AUC baisse vs 0.7217
  => finding « signal repo-spécifique » publié tel quel + architecture de
  scoring par-repo proposée (jamais de mix silencieux).

## Règles inchangées

Labels = tests exécutés (vitest), jamais avis modèle ; source-en-prompt dans
le prompt auteur ; pose sha-vérifiée ; worktrees par (repo,ticket,auteur) ;
journal append-only ; amendements disclosés ; serving v0.7.1/v12 INTACT.
