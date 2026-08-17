# RAPPORT DE RÉVEIL — Night Harvest v1 (en cours, mis à jour par batch)

## Verdicts intermédiaires

| mesure | résultat |
|---|---|
| Découverte tickets réels | 299 candidats (historique OmniRoute complet, 6905 commits) |
| Vérification RED→GREEN | 42 tickets validés / 299 (rejets journalisés : 0 P2P au parent majoritairement) |
| Batch 1 Flash (7 tickets faciles) | 28 appels, 14+/1−, no-diff 46 % ⇒ escalade GLM pré-enregistrée déclenchée |
| Batch 2 GLM (mêmes 7 tickets) | en cours / terminé — voir journal |
| **pooled5 (139 lignes, 104+/35−)** | **PASS poison ext-LOAO jina : AUC 0.7069 IC95 [0.608,0.804], p(<0.60)=1.7 %** |
| Batch 2 GLM (mêmes 7 tickets faciles) | 21 appels, 10 appliqués, 9+/1− : les petits bugs réels restent faciles pour tous les auteurs (confirmation v8 sur du réel) |
| Batch 3 mixte hard-first (GLM 12 tickets + Flash 20 en parallèle) | ~143 appels ; les tickets difficiles produisent enfin des réparations partielles : harvest cumulé 59 appliqués = **37+/22−** (Flash hard est l'usine à négatifs : 23+/49− ; GLM répare mieux : 16+/5−) |
| **pooled5 v2 (172 lignes, 117+/55−)** | PASS : AUC 0.7209, IC95 [0.638,0.797], p(<0.60)=0.002 |
| **pooled5 v3 (206 lignes, 119+/87−)** | **PASS : AUC 0.7223, IC95 [0.649,0.787], p(<0.60)=0.001 — borne basse en hausse continue (0.608→0.638→0.649), négatifs désormais majoritaires** |
| Budget | 294 / 500 appels |

## Trajectoire populations TS (jina space)

pooled2 0.7230 (80) → pooled4 0.7428 (113) → pooled5 0.7069 (139, +26 harvest 24+/2−).
L'AUC baisse légèrement en absorbant les tickets réels (surtout positifs) :
les vrais bugs petits sont faciles pour les auteurs compétents ; les négatifs
doivent venir des tickets difficiles (batch 3 hard-first en cours).

## Critères mix-ready (pré-enregistrés 9092a931)

- poison >= 0.65 ✓ (0.7069) ; IC lo > 0.60 ✓ limite (0.6078) ;
- >= 2 familles TS à >= 5 négatifs chacune : EN COURS (omniroute_real__* est
  une famille par ticket — la notion de strate se juge au niveau agrégé
  omniroute-réel : 35 négatifs pooled5 dont 2 harvest).
- Décision finale : au réveil avec les chiffres définitifs ; serving v0.7.0
  (pool v11) INTACT.

## Suite de la nuit (plan restant)

- verify continue (55+ tickets validés, ~257 candidats restants, garde timeout 240 s active) ;
- fin flash-b2 puis vagues suivantes GLM/Flash sur le backlog hard (budget restant ~329 appels) ;
- prochaine mesure pooled5 à ~250 lignes ; analyse strates + préparation cérémonie v12 en fin de nuit.
- Incident race t9545 réglé (worktrees par (issue,auteur)) ; incident verify-crash réglé
  (timeout par ticket + flush incrémental + re-run).
