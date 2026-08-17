# Window COVERAGE-TS-v14 — Diversité profonde : zod, date-fns synthétique, kimsufi

Status: APPROVED 2026-08-17 — owner « ok pour ta reco, go » (option B post-v13).

## Hypothèse mesurée

Le plafond AUC vient de la monoculture, pas du volume (v13 : leçons DW-43).
La diversité INTER-repos est le dernier levier de données non exploité :
zod profond (validation logique), date-fns synthétique (calcul temporel),
kimsufi-site (propre, doubles) => familles neuves => structure discriminante
neuve pour LOAO-F1 + futures strates Mondrian.

## Cibles (0 re-draw, règle DW-43 scellée)

- zod : discovery élargie (surface <=600L diff, <=1200L fichiers, <=5 fichiers)
  + verified existants non consommés ;
- date-fns : mutants synthétiques doubles/triples (mécanique v7 validée,
  terminaison garantie par design DW-35) ;
- kimsufi-site (own) : doubles synthétiques (runner vitest propre).

## Auteurs (mandat owner continué)

DeepSeek-V4-Flash (principal, 3-4 tirages/ticket), Qwen3.8-2.4T-A95B-NVFP4
(strate négative dédiée, mesurée séparément). Claude/Codex exclus harvest.

## Enveloppe [ratifiée owner « go »]

- Cap **400 appels** (Flash 320 / Qwen 80) ; compteur séparé call-counter-v14 ;
- infra-stop >= 8 erreurs consécutives ; quarantaine <= 10 % ;
- UN tirage utile par (ticket, auteur) : jamais de re-draw (DW-43).

## Mesures scellées

- poison ext-LOAO jina + AUC/IC bootstrap par batch sur pooled7 ;
- populations Qwen3.8 mesurées SÉPARÉMENT avant tout agrégat (DW-37) ;
- pooled7 = pooled6 (546) + lignes v14 ; grille v14 : AUC pooled7 >= 0.72 ET
  IC95 lo > 0.66 => mix v15 représenté en position de force ; sinon bilan
  honnête + pivot encodeur/métrique (la question devient représentation,
  plus données).

## Serving

v0.7.1 / pool v12 INTACT toute la fenêtre ; aucun mix sans cérémonie owner.
