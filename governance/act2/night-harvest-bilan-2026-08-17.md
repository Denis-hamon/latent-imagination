# RAPPORT DE RÉVEIL — Night Harvest v1 (2026-08-17, ~8h autonomes)

## LA nouvelle : pooled5 est MIX-READY, cérémonie v12 préparée à signer

**pooled5 FINAL : 207 lignes TS (119+/88−), AUC jina 0.7227, IC95 [0.652, 0.791],
p(<0.60) ≈ 0 — les TROIS critères mix-ready pré-enregistrés (9092a931) sont
atteints** : poison ✓, IC ✓, 3 familles à ≥5 négatifs (lite 10, usage 8, trc 6).
Proposition v12 ancrée `76e890a9` — **SIGNÉE PAR L'OWNER ET EXÉCUTÉE** :
pool v12 = v11 (219 SWE) + pooled5 définitif (211 TS, récolte figée à 98
lignes harvest 41+/57−) = **430 lignes servies (205+/225−)**, gate 4 volets
PROMOUVABLE, conformal v12 = 7 strates garanties dont omniroute__lite/usage/
affinity (PREMIÈRES strates TS), drill rollback v12→v11→v12 validé HTTP MCP. L'objectif historique « couverture TS » est
désormais à portée de cérémonie.

## La nuit en chiffres

| poste | résultat |
|---|---|
| Mineur tickets réels | clone rendu complet (426 Mo, 6905 commits) ; 299 candidats découverts ; **60 tickets validés** RED→GREEN (rejets journalisés : P2P=0, timeouts, surface) |
| Appels auteurs | **304 / 500** (Flash 3 batches + GLM 3 vagues ; récolte toujours active au réveil sur les derniers tickets) |
| Récolte | 291 tentatives, 94 appliqués labellisés = 39+/55−, no-diff 197 (Flash majoritaire — troncature long contexte) |
| Mesures intermédiaires | pooled5 : 0.7069 (139) → 0.7209 (172) → 0.7227 (207) ; IC : [0.608,0.804] → [0.638,0.797] → [0.652,0.791] |
| Budget | 304 appels ; ~196 restants (fenêtre close au cap ou à décision owner) |

## Découvertes de la nuit

1. **Les vrais bugs historiques petits sont trop faciles** : batch 1 Flash
   (7 tickets faciles) = 14+/1− — confirmation de v8 sur du RÉEL ; les
   négatifs viennent des tickets difficiles (multi-F2P, logique subtile).
2. **Flash sur tickets difficiles = usine à négatifs** (23+/49− au final) :
   il produit des réparations partielles applicables là où GLM répare
   complètement (16+/6−). Les deux auteurs ensemble donnent l'équilibre.
3. **Un ticket 100 % négatif existe** (#repro-10139-cl : 4/4 draws Flash
   négatifs) — les tickets reproducteurs multi-défauts sont la classe dure
   naturelle.
4. Le no-diff Flash (46-67 %) est le prix des longs contextes ; rendement :
   ~1 ligne labellisée / 3.1 appels — acceptable pour la densité.

## Incidents (tous disclosés, journaux append-only)

- **Race t9545 b2/b3** : deux process sur le même worktree ⇒ 4 lignes
  contaminées EXCLUES de pooled5 (note ledger) ; correctif : worktrees
  scopés par (issue, auteur) + idempotence par paire.
- **Verify-crash** : ticket au test RED en boucle infinie a tué le process
  (perte de 42 validations) ; correctif : timeout 240 s par run + try/except
  par ticket + flush incrémental ; re-run complet.
- Amendements ledger : RED≥1 F2P + P2P≥2 (filtre), discover étendu
  (commit-ajout-test sans exigence de n° d'issue dans le sujet).
- DW-42 étendu : cache vitest + parseur TAP (fixés ts_v10_label_exec).

## Reste actif au réveil

- Collecte FIGÉE proprement avant mix (322/500 appels consommés au gel) ;
  239 tickets découverts non vérifiés restent disponibles pour une suite
  (nouvelle fenêtre à ratifier si continuation).
- Flywheel 03:09 UTC : à vérifier (le timer était programmé 2h avant la fin
  de cette collecte ; run d'hier exit 0).
- Verify terminé (60 validés) ; 239 candidats découverts non vérifiés restent
  disponibles pour une suite.

## Trajectoire de session complète (pools TS, espace jina)

pooled1 0.6634 (63, unixcoder 0.6634) → pooled2 0.6739 (80) → pooled4
0.7428-jina (113) → **pooled5 0.7227-jina (207)** : le signal TS est
désormais certifiable, dense et équilibré ; la couverture conforme TS
devient constructible.
