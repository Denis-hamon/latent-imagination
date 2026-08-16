# Window COVERAGE-TS-v6 — négatifs-first, géométrie dédiée (pré-enregistrement v1)

Status: APPROVED 2026-08-16 — option 2 choisie par l'owner en session
(suite au mémo ts-dedicated-geometry : la population TS agrégée 63 lignes
passe la poison gate à 0.6634 mais IC95 [0.49, 0.83] = signal razor ;
l'unique levier démontré est la densité de NÉGATIFS par famille).

## Hypothèse mesurée (le motif de cette fenêtre)

12 négatifs TS existent dans tout l'historique, 9/12 concentrés sur omniroute
— et la classe DIFFICULTÉ INTERMÉDIAIRE (doubles) est le seul mécanisme
validé qui en produit (v5 : 6 négatifs / 12 tirages doubles). Objectif :
**≥ 15 négatifs labellisés supplémentaires** sur des fichiers OmniRoute
non-encore mutés (aggressive, toolResultCompressor, strategySelector,
hardBudget, cachingAware) + ancres positives sur fichiers éprouvés, pour
resserrer l'IC de l'AUC poolée au-delà de 0.60 et rendre la décision de mix
v11 statistiquement défendable.

## Sonde PRÉ-GEL (leçon 14, adaptée)

La classe double est déjà validée (v5). La sonde valide les NOUVEAUX FICHIERS :
2 candidats doubles sur fichiers non-éprouvés × 2 tirages = 4 appels max.
Règle gelée :
- ≥ 1 tirage produit un diff applicable ⇒ fichier validé ⇒ quota construit ;
- 2/2 no-diff ⇒ SWAP de fichier (même classe), jamais forçage ni amendement.

## Construction des candidats (zéro-appel, pré-sonde)

Chaque candidat = (fichier source, fichier test, N remplacements string) vérifié
sur Kimsufi-standard par `node --import tsx/esm --test --test-reporter=tap` :
- F2P cassé par la mutation (obligatoire, sinon rejet journalisé) ;
- P2P ≥ 3 déclarés et verts sur le buggy (obligatoire) ;
- buggy_sha256 enregistré pour le gel de sélection.
Aucune tâche inventée : rejet = journal, jamais silence.

## Quota gelé sous réserve de vérification

- ~12-14 doubles (négatifs-first) sur ≥ 5 fichiers compression/combo ;
- ~3-4 easy sur fichiers éprouvés lite/usageTracking/promptCacheAffinity
  (ancres positives : équilibre de classe garanti) ;
- éventuellement 2 doubles kimsufi-source (repo propre, diversité) — shortfall
  accepté si no-diff ;
- 2 tirages/tâche ⇒ 32-36 slots.

## Choix gelés (identiques v2-v5, par référence)

Auteur épinglé MLX-Qwen3.5-35B-A3B (lignage), classe prompt pilot_run gelée,
problem = SYMPTÔME jamais mutation, extraction strict-git puis patch -l --fuzz
avec pose vérifiée par sha de contenu, labellisation node:test+tsx TAP distante
sérialisée (worktree propre, sha-vérifiée), quarantine ≤ 10 %, provenance
{campaign: coverage-ts-6, window: coverage-ts-v6, author}.
Sources : public-omniroute-ts MIT @ e646fe84 (inchangée) + own-kimsufi-site-ts.

## Enveloppe [dans la plage 120-150 du mémo ratifié option 2]

- Cap : **110 appels** (sonde ≤ 4 + génération ≤ 36 slots + retries/lane
  fuzz-repair). Précédents d'underspend honnête : v4 36/120, v5 34/70.
- Pause-infra ≥ 8 erreurs endpoint consécutives ; stop-au-cap ; shortfall =
  amendement disclosé ; aucun amendement de gate.

## Gates (inchangées, scellées — mesurées sur v6 seul ET sur l'agrégée)

1. Poison ext-LOAO ≥ 0.65 ET classes ≥ 5 lignes chacune ;
2. advprobe 13.5 ≥ 0.5977 (ré-test du candidat clos permis par la nouvelle
   évidence, gate identiquement gelée) ;
3. Critère fenêtre : ≥ 15 négatifs labellisés (sinon shortfall disclosé,
   issue B maintenue) ;
4. Conséquence visée : AUC poolée ≥ 0.65 avec IC95 excluant 0.60 ⇒ décision
   mix v11 défendable puis cérémonie de promotion complète (contrôle v6 exact,
   gate 9.1, drill rollback) — la décision de mix elle-même reste owner.

## Stratification conforme (objectif 20 % @ IC95, lecture 12.x)

Après mix éventuel : calibration conforme v11 avec strates TS (Mondrian ≥ 12
lignes/strate) ; rapport de couverture par strate pour mesurer l'apport TS au
20 % global. Rien n'est promis — mesuré, disclosé.

## Seal record

- frozen_sha256: `b19583e8d4c9517386046b8fdf660a36899d7c73ee45a1f251ac63b929b22d57` (couvre l'état approuvé pré-seal ; identité dans ledger)
- ledger_row: prereg-ledger.jsonl ligne `window-approved` (preuve data/release-store/proofs/window-ts-v6-b19583e8d4c95173.ots)
- approved_by / envelope: Denis (owner), 2026-08-16, option 2 — cap 110 appels.
