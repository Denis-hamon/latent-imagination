# Fenêtre v22 — collecte paires intra-ticket, mitigrations DW-52 (proposition)

Suite logique de v21 (grille manquée, cause = hallucination de contexte sur
fichiers longs) et du minage GitHub en cours (kimi/qwen/epv/tanquery/nx/cqe,
~990 candidats, stock vérifié en croissance). Objectif UNIQUE : produire le
volume de paires intra-ticket qui manque à la reprise (b) DW-51. Aucune
mesure de modèle, aucun serving.

## Mitigations DW-52 figées (le protocole est la variable testée)

1. Sélection tickets à **fichiers source petits** : total src au parent
   ≤ 1200 lignes ⇒ prompt FICHIERS COMPLETS, jamais de troncature tête+queue ;
2. feedback d'application au tour suivant = **l'erreur git apply/patch réelle**
   (très exactement, 400 chars), pas un message générique ;
3. F2P ≥ 2 exigé à la vérification (plus de place pour les partiels) ;
4. boucle 4 tours max, arrêt à convergence (y=1), timeout 240 s, sha-vérif,
   restauration finally (recettes héritées v21/harvest).

## Population (sélection figée avant appels, après round 2 de verify)

≤ 40 tickets vérifiés des nouveaux repos (priorité : kimi, epv, tanquery,
qwen) satisfaisant M1+M3. Si < 20 tickets éligibles ⇒ fenêtre reportée
(pas d'exécution sur stock insuffisant — divulgation au lieu d'appels).

## Modèles & enveloppe

DeepSeek-V4-Pro, Qwen3.8-2.4T-A95B-NVFP4, GLM-5.2-NVFP4 (les 3 comportements
distincts mesurés en v21 ; Flash exclu : 16 % d'application v21 sans gain de
diversité). Cap total 480 appels (40 tickets × 3 modèles × ≤ 4 tours).

## Grille scellée (livraison = données)

- P1 : taux d'application global ≥ 45 % (v21 = 22 % ; sinon les mitigations
  ne tiennent pas et la fenêtre s'arrête au constat) ;
- P2 : ≥ 300 paires intra-ticket à y opposés (seuil de reprise (b) DW-51) ;
- P3 secondaire descriptif : ≥ 5 tickets convergés ET partiels (les deux
  classes sur le même ticket) — la géométrie des réparations graduelles.
P1 ET P2 ⇒ fenêtre réussie, reprise (b) ouverte (fenêtre de modélisation
séparée, décision owner). Sinon ⇒ données conservées, leçon consignée.

## Interdits

Pas de changement de prompt en cours de run ; pas de modèle ajouté après
constat d'échec ; les tickets non éligibles M1/M3 ne participent pas.
