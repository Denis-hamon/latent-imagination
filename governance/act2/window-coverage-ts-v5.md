# Window COVERAGE-TS-v5 — OmniRoute doubles coordonnés (pré-enregistrement v1)

Status: APPROVED 2026-08-16 — option 1 choisie par l'owner en session.
Scellement par ancrage ledger (précédents v1-v4). Piste pré-enregistrée dans
le bilan v4 : « classe de difficulté INTERMÉDIAIRE (doubles mutants) pour
produire des diffs applicables-mais-faux en quantité certifiable ».

## Hypothèse mesurée à tester (le motif de cette fenêtre)

v4 a identifié le plafond : easy → flips (positifs), hard triple → no-diff
(l'auteur ne produit plus rien d'applicable). La classe INTERMÉDIAIRE — deux
défauts coordonnés, chacun dans une région que l'auteur sait réparer seul —
doit produire des diffs APPLICABLES mais FAUX ⇒ négatifs labellisables.
Objectif de classe : ≥ 5 négatifs et ≥ 5 positifs labellisés ⇒ population
certifiable pour la poison gate ET la validation advprobe.

## Sonde de difficulté PRÉ-GEL (avant quota, leçon 14)

1 double mutant × 2 tirages auteur. Règle gelée :
- ≥ 1 tirage produit un diff applicable MAIS non-flippant (y=0 potentiel) ⇒
  classe intermédiaire validée ⇒ quota gelé ;
- 2/2 flips ou 2/2 no-diff ⇒ la classe n'est PAS intermédiaire ⇒ escalade
  déclarée (mixer simple+double dans le quota) ou shortfall accepté — jamais
  de forçage.

## Quota gelé (sous réserve de vérification zéro-appel)

- 8 à 10 tâches « doubles » sur modules à signal vérifié (compression/lite,
  promptCacheAffinity, usageTracking — les 3 modules dont les mutations ont
  produit du signal F2P en v4), max 3 tâches/module, famille omniroute__app.
- 2 tirages/tâche ⇒ 16-20 slots.

## Choix gelés (identiques v2-v4, par référence)

- Auteur épinglé MLX-Qwen3.5-35B-A3B (lignage), classe prompt pilot_run
  gelée, problem = SYMPTÔME jamais mutation, extraction strict-git puis
  patch -l --fuzz, labellisation node:test+tsx TAP distante sérialisée sur
  Kimsufi-standard (sha-vérifiée, worktree propre), quarantine 10 %.
- Provenance {campaign: coverage-ts-5, window: coverage-ts-v5, author}.
- Source `public-omniroute-ts` MIT commit e646fe84 (registrée).

## Enveloppe [ratifiée par l'option-1 owner]

- Cap : **70 appels** (sonde 2 + slots ≤ 40 + retries ; v4 a montré
  l'underspend honnête à 36/120).
- Pause-infra ≥ 8 erreurs endpoint consécutives ; stop-au-cap ; shortfall =
  amendement disclosé.

## Gates (inchangées, scellées)

Poison ext-LOAO ≥ 0.65 ET classes ≥ 5 lignes chacune (sinon dégénérée ⇒
archivé) ; validation prospective advprobe ≥ 0.5977 (certifiable pour la
première fois si les deux classes ≥ 5) ; issue B sinon.

## Seal record

- frozen_sha256: `588be21efd6c5d7ed9c9d4d4cf9969978abc27272b96412f3ab14edea87008f1` (couvre l'état approuvé pré-seal; identité dans ledger)
- ledger_row: prereg-ledger.jsonl ligne `window-approved` (preuve window-ts-v5-588be21efd6c5d7e.ots)
- approved_by / envelope: Denis (owner), 2026-08-16, option 1 — cap 70 appels.
