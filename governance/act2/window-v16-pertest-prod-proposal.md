# Fenêtre v16 — PRODUCTISATION per-test (DW-48), proposition scellée

Suite validée par owner (« go pour la suite ») de DW-47 moitié modèle
VALIDÉ (arm 3896a3e7, médiane Jaccard LOO 0.8333). But : livrer la colonne
« tests prédits échoués » dans compare_patches (Ghost v0.8.0), grounded et
calibrée comme le reste.

## Périmètre (zéro appel LLM)

1. **Recalibration propre** : re-run LOO par ligne sur le dataset figé
   (63 lignes / 446 paires) en conservant les SCORES par paire ; seuil final
   par Youden sur les scores LOO (hors échantillon par construction).
2. **Intégration serveur** : poids logistique + seuil chargés par le serveur
   MCP ; prédiction par candidat = E_diff(candidate) × E_test(noms déclarés
   dans l'execution-plan) ; ligne par test avec probabilité ; ABSTENTION
   (colonne omise) si aucun test déclaré.
3. **Garanties DW-48** : pas de red-set affiché sans proba ; la colonne est
   ADDITIVE (energy_of intouché — preuve par rerun gate 9.1 acc@10).

## Grille de promotion scellée (avant toute mesure)

G1 — LOO AUC paire (scores globaux, pas moyennes de folds) ≥ 0.62 ;
G2 — Brier LOO ≤ Brier du prédicteur constant (p̄ = 140/497 sur dataset 69) ;
G3 — gate 9.1 rerun : acc@10 v12 servi inchangé (référentiel promotion v12 = 0.907 ;
     CORRECTION 2026-08-17 : le prereg écrivait 0.897 par erreur de recopie —
     le référentiel scellé est le volet_2 de promotion-gate-v12.json) ;
G4 — abstention : tout appel sans tests déclarés retourne la colonne vide en
     status `abstained: no declared tests` (test noir, pas de cas construit).
Les 4 conditions requises. Échec ⇒ pas de v0.8.0 ; dataset et arm restent
acquis (DW-47).

## Disclosure d'entrée

- AUC paire interne moyenne = 0.6406 (mesurée v15-dedie) — G1 est proche ;
- frac lignes battues 34 % → la valeur produit est ligne par ligne, la
  colonne porte sa proba pour que le caller tranche ;
- 6 diffs harvest manquants (dataset 63/69) — non reconstruits, figé.

---

## FERMETURE — 2026-08-17 (4/4 gates, promotion exécutée)

Ghost **v0.8.0 servi** : `compare_patches` accepte `declared_tests` et retourne
pour chaque candidat la colonne « tests prédits échoués » — une ligne par test
avec `p_failing` et `predicted_red` (seuil Youden LOO 0.2808). Absence de
tests déclarés ⇒ colonne `abstained` (jamais de devinette). La colonne est
additive : le chemin binaire énergie/calibration est inchangé (G3 rerun 0.907
identique au volet_2 promotion v12).

- G1 LOO AUC paire = 0.842 (≥ 0.62) — λ 1e-2 fixe, disclosure
- G2 Brier LOO = 0.1071 ≤ 0.1788 (constante)
- G3 acc@10 régime servi = 0.907 rerun exact (référentiel corrigé au ledger)
- G4 abstention vérifiée en noir sur le serveur vivant

Cas réel (ticket zed-hosted, 5 candidats partiels, 10 tests déclarés) :
Jaccard live moyen 0.634 — sous la médiane LOO 0.833, cohérent avec l'effet
distributionnel disclosé à la validation (34 % des lignes battent la baseline).
La valeur produit est la proba par test, pas un verdict par candidat.
Détails : `arm-artifacts/promotion-gate-v080-pertest.json`.
