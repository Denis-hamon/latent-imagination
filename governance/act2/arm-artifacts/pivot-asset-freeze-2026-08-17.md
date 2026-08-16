# Gel des actifs — pivot Ghost (PR Simulator), 2026-08-17

Ratifié owner : produit = **Ghost** (le moteur devient le produit), pilote
OmniRoute, ordre P0→P1 validé.

## Actifs gelés comme fondation du pivot

1. **Pool v10 (219 lignes)** = prior global de calibration des sessions
   (chemin node : LI_POOL_JSON/NPZ, servi GHOST v0.5.1).
2. **Conforme Mondrian v0.5.1** (LI_CONFORMAL_CALIB, served_regime,
   disclosures, named_non_coverage) = contrat d'incertitude produit.
3. **Surface MCP ghost v0.5.1** : risk_scan / near_mis_patches / preflight /
   report_outcome / assess — étendue en v0.6.0 par world.compare_patches.
4. **Chaîne d'exécution groundée** : apply strict-git→fuzz sha-vérifiée,
   runners node:test+vitest multi-sources, quarantine rules-v1, ledger
   append-only + OTS, discipline DW-33/35/37/38 (staging-avant-appel,
   terminaison, populations séparées).
5. **Registre sources** : OmniRoute (pilote pivot), zod, date-fns, kimsufi,
   acre, worldmonitor (AGPL restreint).
6. **Sets d'évaluation** : les 11 diffs v9 groundés (2 pos/9 neg) = démo 15.4.
7. **Négatifs archivés non mixés** : populations v2-v9 hors pool (DW-37) —
   réservoir pour futures strates quand densité par classe ≥5 atteinte.

## Ce que le pivot NE change PAS

- Les gates scellées (poison 0.65, advprobe 0.5977 clos, 9.1, classe-min) ;
- l'auteur épinglé comme baseline de contrôle ;
- la calibration conforme servie v0.5.1 (risk_scan inchangé).

## Nouvelle doctrine produit (héritée des leçons v5-v9)

- Toute probabilité affichée ⇒ τ conforme local OU abstention nommée ;
- toute issue ⇒ grounded_by tests-exécutés, jamais avis modèle ;
- calibration par session/repo, prior global en repli divulgué ;
- pas de promesse universelle : couverture mesurée, divulguée, bornée.
