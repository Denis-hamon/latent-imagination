# Window COVERAGE-TS-v7 — négatifs-first multi-fichiers zod + date-fns (pré-enregistrement v1)

Status: APPROVED 2026-08-16 — suite du mandat owner « explorer les repos OSS,
collecter plus de données, jusqu'à ce que ça marche » (ratification option 2,
fenêtre v6 close en PASS poison 0.6714 mais IC n'excluant pas 0.60).

## Hypothèse mesurée

Deux NOUVELLES sources MIT mécaniquement prouvées (zod @5e608851, date-fns
@a0a39220) avec 10 candidats validés zéro-appel (0 écarté) ; la classe double
doit produire des négatifs sur des familles neuves (zod__checks, zod__str,
date_fns__bizdays, date_fns__addDays) => densification + diversification
(futures strates Mondrian fines). Objectif : >= 10 négatifs labellisés
additionnels ; décision mix reste owner-gated par IC.

## Sonde PRÉ-GEL (règle 14, adaptée v6)

Les fichiers candidats sont validés mécaniquement (F2P) mais PAS encore par
l'auteur : sonde = 2 candidats (1 zod string-bounds, 1 date-fns bizdays)
x 2 tirages = 4 appels max. >= 1 diff applicable/tâche => validé ; 2/2 no-diff
=> swap de tâche (jamais de forçage).

## Quota gelé sous réserve de vérification

- 10 tâches validées : 6 doubles (4 zod + 2 date-fns), 4 easy/ancres ;
- 2 tirages/tâche => 20 slots ;
- RÈGLE NEUVE scellée (DW-35) : mutants à terminaison garantie (le candidat
  double_sign_weeks date-fns a été rejeté au design pour boucle infinie).

## Choix gelés (identiques v2-v6, par référence)

Auteur épinglé MLX-Qwen3.5-35B-A3B (lignage), classe prompt pilot_run gelée,
problem = SYMPTÔME jamais mutation, extraction strict-git puis patch -l --fuzz
pose sha-vérifiée, quarantine <= 10 %, provenance {campaign: coverage-ts-7,
window: coverage-ts-v7, author}. Labellisation : VITEST (deux runners : zod =
packages/zod/src/v4/classic/tests, feuilles TAP indent 4 ; date-fns = pkgs/core
depuis le sous-répertoire, feuilles indent >=8 sans accolade finale).
Sources : public-zod-ts MIT @5e608851 + public-date-fns-ts MIT @a0a39220.

## Enveloppe [ratifiée par mandat option-2 continué, dans l'esprit 120-150]

- Cap : 95 appels (sonde <= 4 + 20 slots x ~1.5 + retries) ;
- Pause-infra >= 8 erreurs consécutives ; stop-au-cap ; shortfall disclosé.

## Gates (inchangées, scellées)

Poison ext-LOAO >= 0.65 ET classes >= 5 (sur v7 seul ET pooled3 = 80 + v7) ;
advprobe 13.5 >= 0.5977 (clos, ré-test permis sur évidence neuve) ;
critère fenêtre >= 10 négatifs additionnels (sinon shortfall) ;
mix v11 exige IC95 excluant 0.60 (critère doc v6 inchangé) + décision owner.

## Track parallèle (hors enveloppe v7)

Benchmark endpoint /galere (multi-modèles, ~10-12 calls dédiés, journalisés
dans coverage-bench-author/) => éclairera une proposition de fenêtre v8
multi-auteurs (chaque auteur = population propre, même gate scellée).
