# Window COVERAGE-TS-v3 — worldmonitor, classe triple-coordonnée (pré-enregistrement)

Status: APPROVED 2026-08-16 — lancée par l'owner (« lance la v3 »). Valeurs
gelées, mouvement BY AMENDMENT ONLY avant toute dépense ; scellement par
ancrage ledger (précédents v1/v2).

## Pourquoi (mesuré, trois sondes)

Leçon v2 : l'auteur épinglé répare 94 % des mutants mono-fonction ⇒ quotas
mono-classe ⇒ gates dégénérées. Il faut une classe où l'auteur ÉCHOUE, et un
quota à DEUX classes suffisantes (règle classe min ≥ 5).

**Sondes de difficulté exécutées sur worldmonitor (scripts/_511-rate-limit.mjs,
tests node --test natifs, zéro npm install, 769 tests .mjs au corpus)** :

| classe | résultat auteur | lecture |
|---|---|---|
| mono-point (off-by-one, filtre cassé) | 2/2 réparés | trop facile |
| escalade 1 (priorité ?? inversée ; double-point) | 2/2 réparés | encore trop facile |
| **escalade 2 : TRIPLE coordonné** | **0/1 réparé (no-diff)** | classe validée |

Règle fenêtre v2 appliquée : ≥1 échec ⇒ classe gelée ; max 2 escalades ⇒ la
2e est la dernière, rien au-delà.

## Design du quota — BI-ÉTAGE (pré-déclaré avant toute génération)

La gate poison exige les DEUX classes ≥ 5 lignes. Un quota 100 % triple
donnerait ~0-2 positifs (dégénéré côté positif). Design étagé disclosé :

- **Étage E (easy)** : ~6 mutants mono/double-point sur modules distincts
  (l'auteur les répare ~94-100 % ⇒ classe positive) ;
- **Étage H (hard)** : ~6 mutants triples coordonnés sur modules distincts
  (l'auteur y échoue ⇒ classe négative) ;
- provenance `tier: wm-easy | wm-hard` par ligne, jamais retirée, mesurée
  ensemble au poison-check (la stratification reste visible dans le rapport).
- Famille cible : `worldmonitor__app` (nouvelle ; jamais mélangée avant mesure).

Quota : **12 tâches × 2 tirages = 24 slots** (E:6 + H:6 ; shortfall possible =
disclosure, un plafond n'est pas une garantie).

## Droits & source

`public-worldmonitor-ts` (sources.yaml, commit ef9c8e65…) : **AGPL-3.0-only**
→ analyse + labels dérivés internes AUTORISÉS, republication des patches
INTERDITE. Les diffs générés et les lignes de pool ne vivent qu'en mesure
interne ; rien n'est publié de ce corpus.

## Choix gelés

- Auteur épinglé : MLX-Qwen3.5-35B-A3B-…-bf16 (S12/S14/genfam — comparabilité).
- Classe prompt : pilot_run.gen_patch par référence (contenu .mjs dans la fence
  ```python = mismatch de label de fence, DISCLOSÉ — la classe d'appel reste
  gelée, pas d'amendement prompt).
- Extraction : lane strict-git puis patch -l --fuzz (leçon v2 whitespace),
  pose lointaine vérifiée PAR SHA DU CONTENU (jamais par HEAD/rc).
- Labellisation : node --test TAP sur Kimsufi-standard (worktree worldmonitor
  sérialisé, propre avant/après) ; F2P/P2P nommés ; quarantine cap 10 %.
- Abort : >60 % no-diff ⇒ halt ; ≥8 erreurs endpoint ⇒ pause-infra ; stop-au-cap.

## Enveloppe [ratifiée au lancement]

- Cap : **110 appels** (24 slots × 2 tentatives + sondes + marge incident
  endpoint ; v2 a consommé 20/90).
- Mur : sessions d'autonomie par phase.
- Dépassement : stop-au-cap + shortfall en amendement, jamais silencieux.

## Mesures enregistrées (identiques v2)

1. Poison-check ext-LOAO : AUC ≥ 0.65 ET classes ≥ 5 lignes chacune, sinon
   dégénéré ⇒ quota archivé, jamais mixé.
2. Validation prospective advprobe (13.5) : gate ≥ 0.5977 sur lignes
   worldmonitor jamais vues (non certificatoire si classe < 5 — descriptif).
3. Couverture : table familles avant/après + décomposition par tier.

## Issue B inchangée

Si rien ne survit : v10 reste servi, abstention nommée TS active, quota archivé
pour étude.

## Seal record (remplir à l'approbation + ancrage)

> Identité canonique dans le ledger (précédents 9.3/v1/v2) ; frozen_sha256
> couvre l'état approuvé pré-seal.
- frozen_sha256: `e19a227278f8e64c7cf093e4c4cf81a255b461b9bc5b42c5ab9133c065895025`
- ledger_row: prereg-ledger.jsonl ligne `window-approved` (preuve window-ts-v3-e19a227278f8.ots)
- approved_by / envelope: Denis (owner), 2026-08-16 session — cap 110 appels,
  quota bi-étage 12 tâches × 2 tirages, classe triple-coordonnée validée par
  sondes (mono 2/2, double 2/2, triple 0/1), droits AGPL analyse-interne.
