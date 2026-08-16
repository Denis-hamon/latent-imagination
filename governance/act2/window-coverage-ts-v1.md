# Window COVERAGE-TS — croissance real-work TS/Next.js (pré-enregistrement v1)

Status: PRE-REGISTERED — valeurs gelées ci-dessous, mouvement BY AMENDMENT ONLY
avant toute dépense. Exécution seulement après APPROBATION OWNER de
l'enveloppe (précédent window-gen-families-v1) + ancrage ledger du document
approuvé (précédent 9.3/10.1). Supersède le DRAFT 2026-08-15 (l'option 2 du
draft — abstention nommée sans couverture — reste la sortie de secours si la
source 14.1 ne s'étend pas ; elle est enregistrée ci-dessous comme issue B).

## Pourquoi (mesuré)

- v9/v10 telemetry : 11/11 requêtes TS-monorepo réelles en abstention
  (DRAFT 2026-08-15) ; la couverture TS est le trou mesuré de l'instrument.
- 14.1 a prouvé la source : signal vitest juge-free bout-en-bout sur un repo
  own-rights (acre/blocks, snapshot 0215a8fb…).
- Population jamais vue ⇒ sert AUSSI de validation prospective du candidat
  advprobe (13.5) : les lignes TS ne sont jamais dans le pool au moment où les
  gates 13.1 ont été scellées.

## Source & quotas (gelés)

| Poste | Valeur gelée |
|---|---|
| Source | `own-acre-blocks-ts` (sources.yaml) — modules à suite vitest du package blocks ; mutants par opérateurs sémantiques (swap d'opérandes, inversion de condition, off-by-one bornes, ordre d'arguments) — classe swe-smith répliquée |
| Quota | **10 tâches × 2 tirages = 20 slots** (1–2 mutants par module distinct ; jamais 2 mutants du même test pour éviter les doublons de signal) |
| Famille cible | `acre__blocks` (nouvelle famille dans le pool ; jamais mélangée avant mesure) |

## Choix gelés (par référence, amendment-only)

- **Auteur-modèle épinglé** : identique genfam (MLX-Qwen3.5-35B-A3B-Claude-4.6-
  Opus-Reasoning-Distilled-bf16) — comparabilité des leçons q1, auteur facteur
  de première classe (S11).
- **Classe prompt** : identique genfam/pilot_run.gen_patch par référence
  (diff fences, git-apply strict, retry feedback instrumenté max 1 par slot,
  raw persistée dès le premier appel).
- **Classe extract/vérif — AMENDEMENT DOCUMENTÉ vs py_compile** (checklist du
  DRAFT) : la vérif de compilation est celle du langage — vitest/TS : un diff
  qui ne parse pas ou dont l'application casse la suite à la collecte est
  classé no-diff/unappliable par la chaîne elle-même (suite-error = signal
  honnête, jamais deviné). C'est un changement d'instrument borné à la
  vérification de langue ; la métrique de scoring (LOAO-F1 goal-free) est
  inchangée.
- **Labellisation** : chaîne stricte vitest sur worktree sérialisé (une
  mutation à la fois ; l'arbre doit finir propre — le pilote 14.1 l'exige) ;
  F2P/P2P = tests nommés ; quarantine cap 10 % (LI-LABEL-001) ; labels
  rules-v1 sur la sortie vitest (FR-3 re-dérivable).
- **Provenance** : chaque ligne {campaign: coverage-ts-1, window:
  coverage-ts-v1, author épinglé} — strate jamais mélangée avant mesure.

## Enveloppe budgétaire [ASSUMPTION — ratifier à l'approbation]

- Cap : **80 appels modèle** (20 slots × 2 tentatives + sondes ; leçon q1 :
  l'instabilité endpoint coûte — cap conservateur).
- Mur de temps : une session d'autonomie par phase (génération ; labellisation).
- Dépassement : stop-au-cap + shortfall en amendement, jamais silencieux ;
  pause-infra si ≥8 erreurs endpoint consécutives (politique 10.1).

## Abort & honnêteté (identiques fenêtre gen-families)

- >60 % no-diff après ré-extraction sur un quota ⇒ HALT + diagnostic disclosé.
- Poison-check AVANT mix : ext-LOAO AUC du quota ; **pré-déclaré ici** : si
  une classe du quota a < 5 lignes, la gate est DÉGÉNÉRÉE (précédent flywheel
  v10 : indéfini ≠ conforme) ⇒ quota archivé, NON mixé, pas d'exception.
- Goal-free : E_goal nul explicite ; l'axe gold ne consomme jamais ces lignes.

## Mesures enregistrées avec le quota (avant décision de mix)

1. Poison-check ext-LOAO (AUC ≥ 0.65, ou dégénéré ⇒ archivage).
2. **Validation prospective advprobe (13.5)** : le candidat gelé (h=12,
   λ=1, seed) entraîné sur v10, ÉVALUÉ sur les lignes TS jamais vues
   (LOFO intra-quota) — gate ≥ 0.5977. Résultat publié quel qu'il soit ;
   advprobe ne peut entrer au serving que par une future promotion séparée.
3. Couverture : table familles avant/après + décomposition par provenance.

## Issue B (sortie de secours pré-enregistrée)

Si l'extension de la source échoue (modules insuffisants, signal vitest
instable), la fenêtre se ferme sur un shortfall disclosé et l'option 2 du
DRAFT s'applique : le diagnostic d'abstention NOMME explicitement « famille
TS/monorepo hors couverture » (pas d'abstention générique) — jamais de
fausse couverture.

## Seal record (remplir à l'approbation + ancrage)

- frozen_sha256: (recorded at anchor)
- ledger_row: (recorded at anchor)
- approved_by / envelope: (owner, at session approval)
