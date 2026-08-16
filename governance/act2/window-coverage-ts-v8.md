# Window COVERAGE-TS-v8 — multi-auteurs, usine à négatifs (pré-enregistrement v1)

Status: APPROVED 2026-08-17 — owner « ok go » après bilan v7 + bench endpoint.

## Hypothèse mesurée (motif de cette fenêtre)

v7 a démontré que la difficulté est spécifique à la paire (AUTEUR, FAMILLE) :
l'auteur épinglé répare 9/10 des doubles zod. Hypothèse v8 : des auteurs
DIFFÉRENTS (DeepSeek-V4-Flash, GLM-5.2-NVFP4, Qwen3.8-2.4T-A95B-NVFP4 — tous
producteurs de diffs au bench du 2026-08-16) échoueront PARTIELLEMENT là où
l'épinglé réussit ⇒ usine à négatifs à haut débit (latences 0.6-34 s vs 12-91 s).
Chaque auteur = campagne séparée = population PROPRE, jamais mélangées avant
mesure individuelle par les gates scellées.

## Sonde PRÉ-GEL (adaptée règle 14 : l'inconnu est l'AUTEUR, pas le fichier)

1 tâche éprouvée (zod__checks.single_max_inclusive) × 2 tirages × 3 auteurs =
6 appels max. Règle gelée : ≥ 1 diff applicable/auteur ⇒ auteur VALIDÉ pour la
fenêtre ; 0/2 ⇒ auteur EXCLU (disclosure), jamais de forçage. Les fichiers
zod/date-fns sont déjà validés mécaniquement (v7, 10/10 candidats).

## Quota gelé sous réserve de sondes

Le quota v7 validé zéro-appel est RÉUTILISÉ à l'identique (mêmes 10 tâches,
mêmes buggy_sha256, même staging) — chaque auteur validé reçoit les 10 tâches
× 1 tirage = 10 lignes max/auteur. Provenance par ligne {campaign:
coverage-ts-8-<auteur>, window: coverage-ts-v8, author: <modèle exact>}.

## Mécanique (identique v2-v7 par référence + delta auteurs)

- Même classe prompt pilot_run gelée (problem = symptôme), même extraction
  strict-git → fuzz, pose sha-vérifiée, quarantine ≤ 10 % par campagne ;
- wrapper T=0.7/max_tokens 16000 identique, SEUL le model id change (env
  GENFAM_MODEL) ⇒ la « classe d'appel » reste la même forme ;
- labellisation vitest dual-runner (contrat rules-v1 complet, timeout DW-35) ;
- l'ordre des campagnes est séquentiel par auteur (traçabilité), parallélisme
  interne GENFAM_PARALLEL=4.

## Enveloppe [ratifiée par owner ok-go, cohérente avec DW-38]

- Cap global : **70 appels** (sonde ≤ 6 + 3 campagnes × 10 slots × ~1.5 +
  retries) ; sous-cap scellé 22 par auteur ; pause-infra ≥ 8 erreurs
  consécutives ; stop-au-cap ; shortfall = amendement disclosé.

## Gates (inchangées, scellées — appliquées PAR AUTEUR puis combinée)

1. Chaque population-auteur : poison ext-LOAO ≥ 0.65 ET classes ≥ 5 sinon
   DÉGÉNÉRÉE archivée (attendu : 10 lignes/auteur souvent dégénérées — la
   mesure combinée est l'objectif) ;
2. Population COMBINÉE (3 auteurs × 10 tâches) : mêmes critères ; advprobe
   13.5 ≥ 0.5977 en descriptif (candidat clos) ;
3. DW-37 respecté : aucune population sparse ne rejoint pooled2 ; la
   combinée v8 est mesurée seule, puis en agrégat v8+pooled2 seulement si
   chaque strate-auteur a ses classes ≥ 5 ;
4. Critère fenêtre : ≥ 8 négatifs combinés (l'épinglé en produisait 4/18 sur
   les mêmes tâches ⇒ tout gain est signal d'auteur) ; mix v11 reste
   owner-gated avec IC95 excluant 0.60 (critère inchangé).

## Ce que cette fenêtre ne promet PAS

Aucune promesse d'AUC : si les trois auteurs réparent aussi bien que
l'épinglé, le résultat est un 0-négatif honnête qui FERME l'hypothèse v8.

## Seal record

- frozen_sha256: `f3e7a2f2` (complet dans ledger) — couvre l'état approuvé pré-seal
- ledger_row: window-approved (preuve data/release-store/proofs/window-ts-v8-f3e7a2f2*.ots)
- approved_by / envelope: Denis (owner), 2026-08-17, ok go — cap 70 appels, sous-cap 22/auteur.
