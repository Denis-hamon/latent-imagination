# Mémo — géométrie TS dédiée : état après mesure agrégée zéro-appel

Date : 2026-08-16 (soir). Aucun appel modèle consommé par cette étape.

## Fait nouveau : la population TS agrégée EST certifiable
Les 5 fenêtres TS (ts-1 acre / ts-2 kimsufi / ts-3 worldmonitor / ts-4+5
OmniRoute) contiennent 63 lignes labellisées uniques, 4 repos, **51 y1 / 12
y0** — les deux classes ≥ 5 (règle classe-min satisfaite).
Les 4 collisions d'attempt_id v4/v5 sont des tirages INDÉPENDANTS (2 ont des
labels flipés entre fenêtres : y dépend du patch généré, pas de la tâche).
Aucune ligne supprimée ; champ `window` ajouté à chaque ligne.
Artefacts : `data/landing/act2-pilot/coverage-ts-pooled/` (hors git, opérationnel).

## Mesures sur la population agrégée
| instrument | AUC | gate | verdict |
|---|---|---|---|
| LOAO-F1 goal-free (géométrie du pool, poison check) | **0.6634** | 0.65 | **PASS** (contrôle v9 = 0.6777, même métrique) |
| bootstrap IC95 sur ce 0.6634 | [0.490, 0.830] | — | **statistiquement indiscernable du hasard** |
| advprobe (candidat E13, combinator gelé) | 0.4951 | 0.5977 | non franchie (2e échec certifiable après 0.4286 en v5) |

Répartition des négatifs : omniroute 9/12, worldmonitor 2, kimsufi 1, acre 0.
La densité de négatifs par famille reste LE facteur limitant.

## Lecture
1. **L'inversion est informative** : la géométrie goal-free existante
   (LOAO-F1 sur E_diff) bat le candidat supervisé advprobe sur les deux
   populations certifiables TS. La « géométrie dédiée » n'est pas un nouveau
   classifieur à entraîner — c'est la mécanque existante à nourrir de données
   TS denses en négatifs.
2. **advprobe est mort sur TS** : 0.4286 (v5) puis 0.4951 (pooled). Le
   verdict E13 est confirmé : candidat archivé, rétrogradé, non re-testable
   sans nouvelle évidence.
3. **Le PASS poison est fragile** : marge +0.0134, IC qui inclut 0.49.
   Les règles scellées autorisent techniquement un mix v11 ; la prudence
   épistémique le déconseille tant que l'IC n'est pas resserré par des lignes
   supplémentaires (surtout des négatifs).
4. Dette connue (cosmétique) : la constante `campaign` dans les provenances
   de labels ts-4/ts-5 pointe `coverage-ts-2` (bug de dérivation sed des
   scripts label_exec). Les labels restent valides : ils dérivent des
   run-result mesurés dans chaque propre fenêtre. À corriger dans le prochain
   label_exec dérivé.

## Recommandation (non exécutée — décision owner requise)
Fenêtre TS dédiée NÉGATIFS-FIRST : classe difficulté intermédiaire/double
(validée mécaniquement en v5 : 6 négatifs sur 13), ≥4 modules OmniRoute +
≥1 autre repo, draw redoublé, objectif ≥15 négatifs supplémentaires. Puis
re-mesure : si AUC ≥ 0.65 avec IC resserré excluant 0.60 → mix v11 sur base
solide ; sinon → la couverture TS reste nommée non-couverte (issue B).
Aucune règle scellée amendée ; mix éventuel = cérémonie de promotion complète
(contrôle v6 exact, gate 9.1, rollback drill).
