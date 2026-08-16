# Window COVERAGE-TS-v4 — OmniRoute bi-étage (pré-enregistrement v1)

Status: APPROVED 2026-08-16 — enveloppe ratifiée par l'owner (« j'approuve,
go »). Valeurs gelées, mouvement BY AMENDMENT ONLY ; scellement par ancrage
ledger (précédents v1/v2/v3).

## Pourquoi (mesuré — pilote complet exécuté)

- Source **MIT** (allowlist, droits pleins) : OmniRoute release/v3.8.50,
  commit épinglé `e646fe84…`, **4384 tests unitaires numérotés par issue**
  (bug-fix réels + non-régression), runner node:test/tsx validé vert sur
  Kimsufi-standard. Enregistrée `public-omniroute-ts` (sources.yaml).
- **Sonde de difficulté bi-étage exécutée (leçon 14 scellée)** sur le module
  compression/lite :
  - mutants easy (mono-point) : **2/2 réparés** par l'auteur épinglé ;
  - mutant TRIPLE coordonné : **0/1 réparé** (no-diff) ;
  - ⇒ classe validée : l'étage easy produit des positifs, l'étage hard des
    négatifs — la structure bi-étage de v3, sur une source au catalogue 600×
    plus vaste et sous licence permissive.
- Leçon protocole enregistrée : le champ `problem` doit décrire le SYMPTÔME
  (bug report), jamais la mutation — la sonde initiale l'a démontré (l'auteur
  détecte la contradiction et ne produit rien).

## Quota gelé

| Poste | Valeur |
|---|---|
| Quota | **12 tâches × 2 tirages = 24 slots** (6 easy + 6 hard) |
| Diversité | ≥ 4 modules distincts, max 3 tâches par module (le pilote ne compte que pour la validation de classe, pas pour le quota) |
| Étages | `ts4-easy` : mono-point sur logique testée ; `ts4-hard` : ≥3 défauts coordonnés exigeant une compréhension d'état/interaction |
| Famille | `omniroute__app` (nouvelle, jamais mélangée avant mesure) |

## Choix gelés (par référence, amendment-only)

- Auteur épinglé : MLX-Qwen3.5-35B-A3B-…-bf16 (lignage S12/S14/genfam).
- Classe prompt : pilot_run.gen_patch par référence ; **problem = symptôme**
  (protocole ci-dessus) ; fence ```python sur contenu TS = mismatch disclosé
  (inchangé : pas d'amendement prompt).
- Extraction : strict-git puis patch -l --fuzz (leçons v2/v3), pose vérifiée
  PAR SHA sur le serveur distant, jamais par rc ni par HEAD.
- Labellisation : node --test TAP distant sérialisé sur Kimsufi-standard
  (worktree propre exigé avant/après chaque slot) ; F2P/P2P nommés ; contrôle
  positif rouge obligatoire ; quarantine cap 10 %.
- Provenance : {campaign: coverage-ts-4, window: coverage-ts-v4, tier,
  author} par ligne.

## Enveloppe budgétaire [ASSUMPTION — ratifier à l'approbation]

- Cap : **120 appels** (24 slots × 2 tentatives + sondes santé ; **9 appels
  sonde déjà consommés et audités dans coverage-ts-4/call-log.jsonl**, dont 3
  contaminés par le bug de campaign-dir du pilote — conservés en audit).
- Murs : sessions d'autonomie par phase ; pause-infra si ≥8 erreurs endpoint
  consécutives (politique 10.1).
- Dépassement : stop-au-cap + shortfall en amendement, jamais silencieux.

## Abort & honnêteté (identiques v2/v3)

- >60 % no-diff ⇒ HALT diagnostic ; classe < 5 lignes ⇒ gate poison
  DÉGÉNÉRÉE ⇒ quota archivé, jamais mixé ; advprobe prospective mesurée si
  deux classes, non certificatoire sous le seuil de classe.

## Mesures enregistrées

1. Poison-check ext-LOAO (≥0.65, classes ≥5) avant tout mix.
2. Validation prospective advprobe (gate ≥0.5977) sur ces lignes jamais vues.
3. Si les deux passent ET classes ≥5 : passage en phase de promotion via les
   gates 9.1 (contrôle v6 + régime) — la première promotion TS devient possible.
4. Sinon : issue B (abstention nommée) reste servie, quota archivé pour étude.

## Seal record (remplir à l'approbation + ancrage)

> Identité canonique dans le ledger (précédents 9.3/v1-v3) ; frozen_sha256
> couvre l'état approuvé pré-seal.
- frozen_sha256: `44cbca34fd5dcc87391704387d7b6529333a652c7e65b6f8537975a976b2795b`
- ledger_row: prereg-ledger.jsonl ligne `window-approved` (preuve window-ts-v4-44cbca34fd5d.ots)
- approved_by / envelope: Denis (owner), 2026-08-16 session — cap 120 appels,
  quota 12 tâches × 2 tirages bi-étage (6 easy + 6 hard, ≥4 modules), source
  public-omniroute-ts MIT commit e646fe84, sondes déjà auditées (9 appels).
