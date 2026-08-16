# ACT III — pre-registration package (v1)

Status: PRE-REGISTERED — values move BY AMENDMENT ONLY, logged BEFORE results.
Seal: le sha256 de ce package (état gelé, section Seal non remplie) est ancré
LIVE dans le prereg ledger ; l'identité canonique vit dans le ledger
(convention rct-prereg:159 / ladder-prereg:52 — aucun hash in-file).
Exécution (11.2) seulement après ce scellement. Null-result parity : le verdict
se publie quelle que soit la branche (FR-13).

## Objet

Re-mesure du verdict probe sur le pool grandi v10 (219 lignes, 66 clés-familles,
servi en production). Act II (2026-08-05) : branche (iii) — baseline 0.6271,
jepa 0.5652, bar 0.8889 non franchi. Act III pose la même question avec le même
design gelé sur la géométrie grandie : **une arme franchit-elle le bar ?**
Si oui (i)/(ii) → première émission de certificat live (story 7.5 déverrouillée,
régime strict FR-21). Sinon (iii) → parité null-result, publication signée.

## Ce qui CHANGE vs Act II (déclaré avant mesure)

1. **La base de données** : clean-slice du pool v10 (voir ci-dessous), pas la
   tranche Act II. C'est l'objet même de la re-mesure : la croissance 9–10.
2. **Rien d'autre** : encodage, armes, métrique, bar, marge, split, templates
   et moteur de verdict sont cités par hash, inchangés.

## Base de données gelée

- Pool : `data/landing/act2-pilot/latent-pool-v10.json` (sha `88985eb171b4bb9f…`)
  + `.npz` (sha `80325267404a0761…`) — 219 lignes.
- Base probe = lignes PORTEUSES DE GOLD uniquement : les 12 lignes flywheel
  `goal_free:true` sont EXCLUES de la base Act III (pas de vérité d'exécution
  runnable pour la précision ; R3 — jamais inventer un canal gold). Base =
  207 lignes (positifs = flips gold ; négatifs = tentatives réelles résolues
  faux / synthetic no-flip, classe négatives scellée par l'amendement
  design.toml 2026-08-05).
- Split d'évaluation : règle GELÉE par référence à `[eval_split]` de
  `governance/probe-design/design.toml` (sha `5924ef204cf18c7f…`) :
  repo-grouped + size-stratified, ~20 % des items, ≥2 repos mid-size,
  seed-indépendant ; disjoint familles train/eval. Le split est figé AVANT
  tout entraînement (no-peeking).

## Armes gelées (référence design.toml)

- baseline : régression logistique sur embeddings gelés (sklearn,
  class_weight=balanced, seed fixe), enveloppe hyperparam C ∈ {0.1, 1, 10}.
- jepa-main : énergie latente JEPA, enveloppe hyperparam + budgets scellés
  (lr ∈ {1e-4, 1e-3}, steps ≤ 20k, wall ≤ 2 h node).
- Encodage : `microsoft/unixcoder-base` CLS gelé ( même encodeur que le pool,
  jamais ré-entraîné) ; features = diff rendu + énoncé + tail tests fail
  (`[encoding]` design.toml).
- Règle par arme : verdict par arme JEPA ; meilleure arme JEPA rapportée
  face à baseline (`[arms].per_arm_rule`).

## Métrique, bar, marge, strictness, branches — CITÉS, PAS RECOPIÉS

`governance/probe-design/decision.toml` (sha `6b63eeb0702ae45d…`) fait foi,
BY AMENDMENT ONLY :
- metric = precision_at_recall_floor, CI Wilson 95 %, delta bootstrap percentile.
- registered_bar = 0.8889 (formule coût inchangée) ; min_margin = 0.05.
- verdict : cross = `precision >= bar` (inclusif — régime verdict) ; le régime
  BLOCKING (FR-21, émission certificat) reste `strictement >` : les deux
  strictness coexistent, jamais unifiées (doctrine projet n°6).
- branches : i = ship JEPA ; ii = bar franchi sans marge → baseline +
  comparaison honnête ; iii = aucune arme ≥ bar → mesure seule.

## Templates de verdict PRÉ-ANCRÉS (trois, pour les trois branches)

`governance/probe-design/verdict-templates/` — rendu mécanique seul autorisé
(`render_verdict_document` refuse tout autre template) :
- `win.md` (branche i) sha `d07f4c8a35cbb8f6…`
- `null.md` (branche ii) sha `e08d7a84ae231caa…`
- `measurement-only.md` (branche iii) sha `a68b5c9f24af3efc…`
Moteur : `packages/probe/src/probe/verdict.py::compute_verdict` (aucun
override manuel possible par construction).

## Garde anti-peeking

Aucun résultat d'arme n'est observé avant l'application de la règle d'arrêt
enregistrée : le split est gelé avant entraînement ; les métriques d'eval ne
sont calculées qu'une fois, sur le split gelé ; tout regard intermédiaire sur
l'eval = amendement loggé AVANT de continuer (précédent design.toml 2026-08-05 :
« accounting must happen before outcomes are seen »).

## Enveloppe budgétaire [ASSUMPTION — ratifiée]

- **0 appel modèle auteur** : Act III est une mesure OFFLINE (pool v10 déjà
  labelisé juge-free) — aucune dépendance endpoint, aucune dépense API.
- Compute : baseline ≤ 30 min CPU ; jepa ≤ 2 h GPU node ; enveloppes héritées
  de `[hyperparameter_envelopes].budgets` (design.toml), pas étendues.
- Deadline wall : une session d'autonomie (pattern autonomy_8h.sh).
- Dépassement : stop au cap + publication partielle avec pourcentage couvert
  dans le header (règle disclosure de budget-v1.toml), jamais d'extension
  silencieuse.

## Procédure d'amendement — prouvée par précédent

Toute modification de ce package après scellement est un AMENDEMENT : loggé
dans le ledger avant résultat, hash du package re-ancré, raison écrite.
Le précédent contraignant existe : les deux amendements 2026-08-05 de
design.toml (`[eval_split]` et `[negatives_class]`), faits post-scellement,
pré-entraînement, sur dossier, jamais en silence.

## Seal record (fill at ledger-anchoring ceremony)

- frozen_sha256: `9ba6401770c41d2c69b7cc6ac1998488a324daf32e13e9f2a23c9055006c6c75`
  — couvre ce document en état gelé (Seal record non rempli) ; l'identité
  canonique vit dans le ledger (prereg-ledger.jsonl, ligne
  `type:"prereg-package"`, ancrée 2026-08-16T11:18:30Z, mode ots-live), pas
  in-file (convention rct/ladder).
- ledger_row: data/release-store/prereg-ledger.jsonl — `prereg-package` (chain_hash = frozen_sha256)
- ots_proof_ref: data/release-store/proofs/act3-9ba6401770c41d2c.ots
- code_commit: `0f76f5f2385332d2d46e1b6140500f61d081601e`
