# Fenêtre v15 — supervision per-test
Status: APPROVED 2026-08-17 — owner « ok go ».
(Proposition d'origine conservée ci-dessous, complétée par cet encadré.)

## Encadré ratifié

- Enveloppe : **300 appels** (Flash ~200, Qwen3.8 ~100) ; compteur v15 séparé.
- Deux campagnes : A = triples synthétiques >= 8 F2P (pipeline genfam+label
  v15 FULL-OUTCOMES), B = tickets réels >= 4 F2P (pipeline harvest patché
  full-outcomes). Multi-tirages par tâche AUTORISÉS (5-6) : en supervision
  per-test chaque pattern d'échec partiel est un label DISTINCT — DW-43 ne
  s'applique pas (il protège l'AUC binaire, pas la granularité per-test).
- Objectif dataset : >= 100 lignes à set-de-tests-rouges nommé (avec les 41
  existantes => ~140+) ; la cible 150 du texte initial est indicative.
- Bras de mesure Jaccard : pré-enregistré APRÈS constitution du dataset,
  AVANT toute modélisation (baseline triviale scellée).
- Serving Ghost v0.7.1/v12 INTACT.


## Motif (issu de la clôture d'arc perception, 54f79ad + cbc6133)

Sous supervision binaire (y = passe/passe-pas), la perception et la métrique
sont au plafond mesuré (0.69-0.75 global ; intra-famille quasi-aléatoire ;
les 4 encodeurs testés hiérarchisés code-spé > généraliste). Le prochain
signal est plus riche : **prédire QUELS tests échouent**, pas seulement si.
Données déjà sur disque : 201/205 run-results conservent les issues nommés
par test ; 41 réparations partielles nommées ; 4 tâches multi-patterns
(lite.triple x3 patterns) => le signal per-test EXISTE, le volume manque.

## Design proposé

1. **Labeler full-outcomes** : extension du label exec pour capturer l'issue
   COMPLET par test (sans troncature) — les anciens run-results restent
   exploitables via tails (201/205).
2. **Collecte ciblée** : 15-20 tâches triples/hard à >=4 F2P (OmniRoute
   prioritaire — familles denses), Flash x 5-6 tirages (ici les multi-tirages
   sont des FEATURES : chaque pattern d'échec partiel = un label distinct ;
   DW-43 ne s'applique pas à cette supervision).
3. **Dataset** : >= 150 lignes partielles (patch, set-de-tests-rouges).
4. **Bras de mesure pré-enregistré** : LOAO prédiction de l'ensemble-rouge
   (Jaccard / précision par test), jamais de label deviné, grille scellée
   avant mesure, promote seulement si > baseline triviale (prédire
   l'ensemble complet des F2P déclarés) avec marge scellée.

## Produit si succès

compare_patches v2 : colonne « tests prédits échoués » par candidat —
l'artefact exact de la vision PR-Simulator (Table Option/Tests prédits/
Risque), grounded et calibré comme le reste.

## Enveloppe estimée

200-300 appels Flash (rendement triples ~0.45 label/appel) + travail
labeler/mesure zéro-appel. Décision owner requise.

---

## FERMETURE — 2026-08-17 (bilan scellé)

**Budget consommé** : A synth 55 flash + 30 qwen (gen) + 31 label runs ;
B réels 42 draws flash. Cap 300 respecté (~160 appels équivalents).

**Rendement** :
- A synth : flash 16 ok / 19 no-diff / 7 budget-stopped ; qwen 15 ok / 6 no-diff.
  Quarantaine 0%. Labels A : y=1 24, y=0 7.
- B réels (7 tickets >=4 F2P, draws d5-d10) : 59 appliqués, 51 partiels nommés.

**Dataset per-test** : 82 lignes, 58 partielles (v15-label 7, harvest-full 19,
legacy-reconstruit 32) — shortfall disclosé vs ~150 visé.

**Arm Jaccard (prereg ef8ca091)** : CLOS. Médiane B3 (voisin-1, exclusion
tâche) = 0.0000 vs baseline B1 (declared_f2p) = 0.6667. La géométrie E_diff
ne généralise PAS le red-set au-delà de la tâche ; seul le voisinage
même-tâche transfère (trivial : mêmes tests). 38% des lignes montrent un
transfert partiel hors-tâche mais sous la marge scellée de +0.05.
Détails + toutes disclosures dans
`governance/act2/arm-artifacts/arm-pert-test-jaccard-verdict-2026-08-17.json`.

**Actifs conservés** : dataset `pert-test-dataset/` (58 red-sets nommés),
labeler `ts_v15_label_exec.py` (tiers d'un futur modèle per-test non-E_diff),
harvest `--min-f2p` et full-outcomes.

**Conséquence produit** : la colonne « tests prédits échoués » de
compare_patches v2 reste hors de portée du voisinage latent ; elle exige un
modèle dédié (DW-47). La fenêtre v15 ferme sans promotion ; v12 reste servi.
