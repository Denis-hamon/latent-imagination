# GATES CANDIDATS ext-LOAO — pré-déclarés AVANT toute mesure candidate (13.1 AC)

Status: SEALED 2026-08-16 — amendment-only après ce commit. Toute modification
après le premier run candidat est un amendement loggé (précédent design.toml).

## Baseline mesurée (instrument courant, pool v10 gelé, 0 appel)

`ext-loao-benchmark-v10.json` :
- **ext-LOAO strict (famille entièrement held-out, seuil réappris sur train) :
  AUC 0.5477, acc 0.4018** (219 lignes, 55 familles) — c'est LA référence des
  gates, pas le 0.750 de la décomposition S14 (protocole plus lâche : seuil
  global, exclusion propre-tâche seulement). L'écart est publié, pas lissé :
  la géométrie courante ne transfère quasi pas hors famille.
- in-family LOAO de référence : AUC 0.6694, acc 0.6027.
- Contrôle v6 GOLD : 0.822/0.779 exact.

## Gates (métrique, marge, tie-rule)

1. **Métrique de promotion** : AUC ext-LOAO strict (harness `scripts/act2/
   ext_loao.py`, seuils par fold réappris sur train, famille entière exclue).
2. **Marge de franchissement** : AUC_candidat ≥ baseline_strict + **0.05**
   (soit ≥ 0.5977 contre 0.5477). Un candidat sous la marge est ENREGISTRÉ
   avec son artefact, jamais promu (résultat négatif publié même layout).
3. **Garde home-regime** : in-family LOAO AUC_candidat ≥ 0.6694 − **0.02** —
   un candidat n'achète pas le transfert en détruisant le régime domestique
   (leçon E2/S9 citée : la destruction du home regime n'est pas du progrès).
4. **Tie-rule** : égalité (à ±1e-4) ⇒ la baseline gagne ; pas de promotion au
   tie jamais.
5. **Contrôle d'intégrité** : v6 GOLD 0.822/0.779 ±(0.01/0.005) rejoué avec
   chaque mesure candidate.
6. **Promotion prospective seulement** (leçon S13) : un candidat qui franchit
   les gates est ENREGISTRÉ pour validation sur données jamais vues (story
   13.5) ; la géométrie servie ne change PAS sur la foi du pool qui l'a testée.

## Ce qui est interdit après ce scellement

- Changer la métrique, la marge, la tie-rule ou le protocole de fold pour un
  candidat qui échoue (amendement loggé AVANT re-mesure seulement).
- Sélectionner le meilleur sous-ensemble de familles après coup (le benchmark
  est agrégé sur TOUTES les familles ; les rapports par famille sont du
  diagnostic, pas une base de sélection).
