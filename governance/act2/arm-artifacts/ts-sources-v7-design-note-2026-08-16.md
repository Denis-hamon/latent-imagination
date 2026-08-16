# Note de design — sources TS de génération v7+ (autonomie owner 2026-08-16)

Mandat owner : « explorer des repos OSS GitHub, collecter beaucoup plus de
données, les rentrer dans de plus gros pools jusqu'à ce que ça marche ».

## Sources enregistrées ce jour (registry commité)

1. **public-zod-ts** — colinhacks/zod @ `5e608851` (MIT vérifié,
   packages/zod/LICENSE). Clone Kimsufi `~/zod-source`, pnpm install OK,
   runner validé : `npx vitest run packages/zod/src/v4/classic/tests/string.test.ts`
   → 94 tests verts (~7.5 s). Surface de mutation identifiée :
   `src/v4/core/checks.ts` comparaisons inclusive/exclusive (l.80 max :
   `def.inclusive ? payload.value <= def.value : payload.value < def.value`,
   l.131 min idem) + regexes.ts + dates. Fichier test par domaine
   (number/date/datetime/enum...). Famille cible `zod__v4`.
2. **public-date-fns-ts** — date-fns/date-fns @ `a0a39220` (MIT vérifié,
   pkgs/core/LICENSE.md — absent à la racine, d'où license=None dans l'API).
   Clone Kimsufi `~/date-fns-source`. Runner validé depuis **pkgs/core** :
   `npx vitest run src/addDays/test.ts` → 9 passed / 7 skipped (173 ms).
   Structure : ~350 fonctions pures, chacune `src/<fn>/{index.ts,test.ts}`
   ⇒ families Mondrian fines naturelles (date_fns__<fn>). Logique
   frontalière temporelle/numérique idéale pour doubles négatifs-first.

## Rejetées et pourquoi (traces d'audit)

- **date-fns racine** : d'abord suspectée sans licence (LICENSE absent à la
  racine, API `license: None`) ⇒ vérification manuelle ⇒ licence dans
  `pkgs/core/LICENSE.md` (MIT) ⇒ acceptée.
- **marked** : LICENSE.md 404 sur master, statut licence non confirmé en
  ligne ⇒ non retenue sans vérification supplémentaire (jamais de source
  sans licence vérifiée — précédent AGPL worldmonitor montre le coût des
  restrictions).

## Mécanique mutants pour la fenêtre v7 (à construire)

- zod : doubles inclusif/exclusif sur checks.ts (min + max, ou max + regex),
  tests dédiés par domaine comme F2P ; vitest --reporter=tap pour les noms
  de tests (adapter le parseur TAP du quota script : vitest TAP ≠ node:test TAP).
- date-fns : doubles sur bornes (ex. addMonths fin-de-mois + isLeapYear),
  `test.ts` par fonction ; runner depuis pkgs/core.
- Quota visé v7 (pré-probe) : ~8-10 candidats par source validés zéro-appel,
  sonde 2/source, puis génération doubles × 2-3 tirages.

## Résultats pilote zero-call zod OBtenus ce jour (3/3 validés, worktree restauré)

| candidat | classe | F2P | P2P |
|---|---|---|---|
| zod__checks.double_inclusive_bounds | double | 7 (.gte/.min/.lte/.max/.nonpositive/.nonnegative...) | 51 |
| zod__checks.bound_and_tightening | double | 4 (.lte/.max/.nonpositive/max value getters) | 54 |
| zod__checks.single_max_inclusive | easy | 3 (.lte/.max/.nonpositive) | 55 |

Parseur TAP vitest validé (lignes indentées `    ok|not ok N - nom`).
date-fns : 2/3 candidats validés zéro-appel (worktree restauré propre) :

| candidat | classe | F2P | P2P |
|---|---|---|---|
| date_fns__bizdays.weekend_counted | easy/double | 9 | 10 |
| date_fns__addDays.amount_subtracted | easy | 3 | 6 |
| date_fns__bizdays.double_sign_weeks | REJETÉ | — | — |

**RÈGLE NEUVE (scellée dans le design fenêtre)** : un mutant ne doit jamais
pouvoir créer une boucle non terminante — `double_sign_weeks` inversait le
sign du compteur journalier ⇒ itération infinie sur les tests long-range
(vitest zombie à 100 % CPU observé, kill -9 + git restore ; P2P=0 = le
parseur n'a jamais vu la fin). Toute conception de mutant doit vérifier la
terminaison avant validation ; parseur TAP vitest : feuilles = indent ≥8
espaces SANS `{` final (les describe-wrappers et file-level sont exclus).

## Ce qui n'est PAS décidé

- Aucune enveloppe d'appels v7 ratifiée ; la note n'engage aucun budget.
- L'adaptation du parseur TAP vitest et du stage/quota par source est un
  travail de fenêtre (scripts dérivés ts_v7_*), pas fait ce jour.
