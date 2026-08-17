# PROPOSITION v12 — mix du pool servi avec pooled5 (PRÉPARÉE, NON EXÉCUTÉE — décision owner)

État au réveil 2026-08-17 : les critères MIX-READY pré-enregistrés (9092a931)
sont ATTEINTS. Ce document prépare la cérémonie ; rien n'est servi tant que
l'owner ne signe pas.

## Pourquoi c'est prêt

| critère scellé | mesure |
|---|---|
| poison ext-LOAO ≥ 0.65 (jina) | **0.7227** |
| IC95 borne basse > 0.60 | **0.652** [0.652, 0.791], p(<0.60)≈0 |
| ≥ 2 familles TS à ≥ 5 négatifs | **3 familles** : omniroute__lite (10 neg/15), omniroute__usage (8/18), omniroute__trc (6/6) |

pooled5 = 207 lignes (119+/88−) : fenêtres v1-v10 (mutants) + night-harvest
(94 lignes issues de 60 tickets RÉELS minés dans l'historique OmniRoute —
SWE-bench-style, vérité terrain git-historique, zéro mutant inventé).

## Design de mix proposé (cérémonie v12, à signer)

1. **pool v12 = backbone v11 (219 lignes SWE/flywheel) + pooled5 (207 lignes
   TS)** = 426 lignes ; append-only ; provenance par ligne conservée.
2. Premières STRATES MONDRIAN TS à garantie propre : lite (15 lignes) et
   usage (18 lignes) passent le N_MIN=12 ⇒ calibration conforme par famille
   pour ces deux strates (le reste : fallback poolé divulgué).
3. Gate 9.1 : acc@10 % régime servi ≥ v11−0.01 ; contrôle v6-GOLD recalculé
   dans l'espace jina (ancre 0.8315/0.7793 attendue ±0.01) ; conforme réalisé
   ≤ garanti par strate.
4. Déploiement drop-in pool-v12.conf ; DRILL rollback v12→v11→v12 validé par
   HTTP MCP (précédent v11) ; GHOST v0.6.x→v0.7.x : champ pool/encoder déjà servi.
5. L'objectif historique « 20 % de couverture @ IC95 sur TS » devient alors
   MESURABLE : coverage conforme par strate TS sur le pool servi.

## Garde-fous hérités

- Aucune ligne des populations rejetées/dégénérées (v7/v8, qwen-bras, lignes
  contaminées t9545-glm exclues) n'entre dans v12.
- advprobe reste clos ; pas de candidat supervisé dans le mix.
- Le noyau produit Ghost v0.7.0 (compare_patches + risk_scan) continue de
  servir pendant toute la cérémonie (drop-in = swap atomique).

## Coût estimé de la cérémonie

~0 appel modèle : ré-embedding déjà fait (pooled5 jina + v11 jina), calibration
numpy/torch local, drill = requêtes HTTP. Décision = signature owner.
