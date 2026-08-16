# Window COVERAGE-TS-v2 — fenêtre TS sur source Kimsufi (pré-enregistrement v1)

Status: APPROVED 2026-08-16 — lancée par l'owner en session (« lance la v2 »).
Valeurs gelées, mouvement BY AMENDMENT ONLY avant toute dépense ; scellement
par ancrage ledger ci-dessous (précédents gen-families-v1 / coverage-ts-v1).

## Pourquoi (mesuré)

- Issue E14 v1 : quota TS mono-classe positive (14/14 flips — l'auteur épinglé
  répare toutes les mutations locales d'acre) ⇒ poison gate et validation
  advprobe DÉGÉNÉRÉES ⇒ quota archivé. Leçon scellée (rétro 14) : un quota
  mesurable exige des tâches où l'auteur ÉCHOUE parfois.
- Nouvelle source enregistrée : `own-kimsufi-site-ts` (serveur Kimsufi-standard,
  snapshot e1df27a5…) : monorepo Astro/TS, 53 specs vitest, 1663 tests verts,
  modules logiques profonds (content-adapters : rendu Drupal 43 tests,
  transformers 28, buildComponents 15…) — classe de difficulté au-dessus des
  mutants one-function d'acre.
- Population jamais vue ⇒ valide AUSSI la candidate advprobe (13.5) si deux
  classes existent à la fin.

## Protocole DIFFICULTY-PROBE (pré-déclaré, leçon 14 — AVANT gel du quota)

1. Deux mutants pilotes sur les modules les plus durs (content-adapters),
   chaîne vérifiée d'abord zéro-appel (bug → F2P nommés rouges → gold reverdit).
2. Deux générations auteur (modèle épinglé, T=0.7, classe prompt pilot_run
   gelée) sur ces mutants, loggées au call-log de la fenêtre.
3. Règle de décision gelée :
   - **≥ 1 échec auteur sur 2** ⇒ la classe de difficulté est la bonne :
     le quota est gelé sur cette classe.
   - **2/2 réparés** ⇒ escalade de difficulté déclarée (mutants multi-fonctions
     / inter-modules) AVANT de geler ; la sonde est re-jouée (max 2 escalades,
     ensuite shortfall accepté et disclosé plutôt que de forcer).

## Quota & choix gelés

| Poste | Valeur |
|---|---|
| Source | `own-kimsufi-site-ts` (+ max 2 tâches acre hors diff3-merge déjà couvert) |
| Quota cible | 10 tâches × 2 tirages = 20 slots |
| Auteur épinglé | MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-bf16 (S12/S14/genfam) |
| Classe prompt | pilot_run.gen_patch par référence (inchangée) |
| Classe extract | amendment documenté v1 : vitest/TS (comme v1) |
| Labellisation | chaîne vitest stricte DISTANTE sur Kimsufi (sérialisée, arbre propre exigé avant/après chaque slot) ; F2P/P2P nommés ; quarantine cap 10 % |
| Famille cible | `kimsufi__site` (+ `acre__blocks` résiduel) — jamais mélangées avant mesure |

## Enveloppe budgétaire [ratifiée par le lancement owner]

- Cap : **90 appels** (sonde 4 + quota 20 slots × 2 tentatives + sondes santé ;
  v1 a prouvé l'underspend honnête à 24/80).
- Mur : sessions d'autonomie par phase.
- Dépassement : stop-au-cap, shortfall = amendement disclosé ; pause-infra si
  ≥ 8 erreurs endpoint consécutives.

## Abort & honnêteté (identiques v1)

- > 60 % no-diff après ré-extraction ⇒ HALT diagnostic.
- Poison-check AVANT mix ; classe < 5 lignes ⇒ gate DÉGÉNÉRÉE ⇒ quota archivé,
  jamais mixé (règle scellée, pas d'exception).
- Validation prospective advprobe (13.5) rejouée si deux classes : gate ≥ 0.5977.
- Goal-free : E_goal nul explicite, axe gold jamais consommé.

## Issue B (inchangée, déjà servie)

Si aucun quota ne survit : GHOST v0.5.1 continue de NOMMER la non-couverture
TS ; le registre KNOWN_TS_FAMILIES est étendu aux nouvelles strates archivées.

## Seal record (remplir à l'approbation + ancrage)

> Le frozen_sha256 couvre l'état APPROUVÉ (seal record non rempli) ; identité
> canonique dans le ledger (précédent 9.3).
- frozen_sha256: `ebfe7acf9e7bf62e81c106b1dae1a1dc7b93c0840c04d80958ed361707a824b4`
- ledger_row: prereg-ledger.jsonl ligne `window-approved` (ancrée 2026-08-16T12:22:55Z, preuve `data/release-store/proofs/window-ts-v2-ebfe7acf9e7bf62e.ots`)
- approved_by / envelope: Denis (owner), 2026-08-16 session — lancement direct :
  enveloppe 90 appels, difficulty-probe pré-quota, règles d'escalade et de
  shortfall telles qu'enregistrées ci-dessus.
