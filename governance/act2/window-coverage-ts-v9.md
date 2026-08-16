# Window COVERAGE-TS-v9 — Flash x triples hard, A/B (pré-enregistrement v1)

Status: APPROVED 2026-08-17 — owner « go avec tes recos » (tirages Flash 3 /
épinglé 2, cap 55, scope 5 triples OmniRoute, pas de 3e bras).

## Hypothèse mesurée

v8 a réfuté « auteur faible = négatifs » sur tâches intermédiaires. v9 teste
la case jamais explorée : **modèle rapide (DeepSeek-V4-Flash, 0.6 s) sur les
cas les plus complexes** (triples coordonnés v4, jamais générés avec
source-en-prompt) vs **auteur épinglé sur les MÊMES tâches**. Critère « on
peut l'épauler » : taux de négatifs Flash strictement > taux épinglé sur
tâches identiques; sinon hypothèse close.

## Tâches (héritage v4 — 5 triples, réutilisés à l'identique, strings vérifiés
présents 1x dans le commit OmniRoute épinglé)

lite.triple_coordinated (8169), combo.triple_gate (8376),
combo.triple_skiporder (8376), affinity.triple_coordinated (8370),
usage.triple_coordinated (8331). Runner node:test+tsx TAP (chaîne v2-v6).
Aucun flip de boucle au design => risque DW-35 nul par construction.

## Sonde PRÉ-GEL (<= 4 appels)

2 tâches (combo.triple_skiporder, affinity.triple_coordinated) x (Flash x1,
épinglé x1). Règle gelée par (auteur, tâche) : >=1 diff applicable => bras
validé ; 0 => auteur EXCLUSIF de cette tâche (disclosure, jamais forçage).

## Enveloppe [ratifiée owner]

- Cap global **55 appels** ; sous-caps scellés : campagne flash <= 30,
  campagne épinglé <= 25 (budget par répertoire, journal séparé) ;
- Flash <=3 tirages/tâche (15 slots), épinglé <=2 tirages/tâche (10 slots) ;
- pause-infra >= 8 erreurs consécutives ; stop-au-cap ; shortfall disclosé.

## Disciplines inchangées

Classes prompt/extract gelées (seul model id change par bras), provenance par
ligne {campaign, window, author=<model exact>}, labellisation rules-v1 avec
protection timeout DW-35, quarantaine <=10 % par campagne, DW-37 : les deux
bras sont des populations SÉPARÉES, mesurées seules, jamais mixées au pooled2.

## Gates (scellées) & verdict

1. Poison ext-LOAO >= 0.65 ET classes >=5 PAR POPULATION-BRAS (attendu
   dégénéré à 10-15 lignes — disclosure, pas d'exception) ;
2. MESURE PRINCIPALE : négatifs_flash/n_flash vs négatifs_pinned/n_pinned à
   tâches identiques ;
3. Si Flash confirme (taux négatif nettement supérieur ET >= 5 neg labellisés)
   => proposition v10 : production massive Flash x triples (enveloppe separate,
   owner-gated) vers la densité mix v11 ; sinon hypothèse close, bilan publié.
4. advprobe descriptif seulement si classe certifiable (candidat clos).
