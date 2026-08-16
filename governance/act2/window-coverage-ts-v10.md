# Window COVERAGE-TS-v10 — fenêtre PRODUCTION Flash x triples (pré-enregistrement v1)

Status: APPROVED 2026-08-17 — owner « ok go » ; synthèse des leçons v6-v9 +
bras embedder (DW-41 : jina-v2-base-code 0.7230 non certifiable faute de
lignes => produire les lignes).

## Hypothèse mesurée

1. La classe TRIPLE + source-en-prompt est une usine à négatifs valide pour
   TOUT auteur compétent (v9 : 82% neg, Flash 5/7 et épinglé 0/4) ;
2. DeepSeek-V4-Flash seul (0.6-2 s/appel, validé v8+v9) peut produire une
   population TS certifiable équilibrée (~40 slots) à coût temporel trivial ;
3. pooled4 (pooled2 80 + v9 11 + v10 >= ~35) doit atteindre >= 5 par classe
   ET densité suffisante pour resserrer l'IC de l'AUC ext-LOAO.

## Quota (tâches RÉUTILISÉES sha-vérifiées + 4 triples neufs validés zéro-appel)

- 7 TRIPLES : 3 OmniRoute v9 validés (lite/affinity/usage) + 4 neufs
  (trc, hb, zod-number, date-fns-bizdays — règle DW-35 terminaison au design) ;
- 13 EASY/DOUBLES réutilisés de v6/v7 (buggy sha identiques) : équilibre
  positif/négatif par famille ;
- Flash : 3 tirages/triple, 2 tirages/double-easy => ~47 slots ;
- AUTEUR UNIQUE : DeepSeek-V4-Flash (population mono-auteur propre).

## Sonde PRÉ-GEL (<= 4 appels)

2 tâches (1 triple NEUF trc + 1 triple neuf date-fns) x Flash x1 tirage =>
2-4 appels. >=1 diff applicable par fichier => validé ; 0 => swap fichier.

## Enveloppe [ratifiée owner ok-go]

Cap **80 appels** Flash (sonde <=4 + ~47 slots x ~1.4 + retries) ; pause-infra
>= 8 erreurs consécutives ; stop-au-cap ; shortfall disclosé.

## Gates (scellées, inchangées)

Poison ext-LOAO >= 0.65 ET classes >= 5 : mesurée sur v10 seul ET sur pooled4 ;
advprobe descriptif seulement (candidat clos) ; pooled4 devient la population
de référence du bras re-test jina (DW-41) SI >= 160 lignes certifiables —
sinon la suite logique est une v11 de production, pas l'indulgence.

## Interdits

Aucune ligne v9/v10 ne rejoint pooled2 ; pooled4 = agrégation MESURÉE séparée
avec sa propre gate (DW-37) ; jina jamais servi/mixé sans bras de migration
complet re-pré-enregistré.
