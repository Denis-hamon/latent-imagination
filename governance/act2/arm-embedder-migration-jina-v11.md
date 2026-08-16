# Bras MIGRATION — pool v11 sous jina-v2-base-code (pré-enregistrement)

Ouvert par le verdict PROMOUVABLE du re-test df5aa51e+addendum (jina 0.7428
[0.640,0.840] vs unixcoder 0.6951 sur pooled4, grille franchie). Ce bras ne
change AUCUNE ligne du pool : mêmes 219 lignes v10, mêmes textes, seul
l'encodeur change => nouvelle géométrie de coordonnées, calibration complète
à refaire (jamais de réutilisation des seuils unixcoder).

## Protocole gelé

1. **Re-embed v10** : textes EXACTS de latent-pool-v10.json (state, diff,
   gold si non goal_free ; E_goal=0 explicite pour les 12 lignes goal_free —
   convention R3 inchangée) ; jina-v2-base-code local GPU node (shims chargement
   documentés DW-sweep, pooling last-token natif, max_length 8192).
2. **latent-pool-v11** : rows identiques à v10 + champ `encoder:
   jina-v2-base-code` ; idempotent append-only (jamais d'écrasement).
3. **Ancre d'échelle NOUVELLE** : v6-GOLD re-mesuré dans l'espace jina (AUC +
   acc@100) = valeur d'ancrage enregistrée, PAS comparée à 0.822/0.779
   (espaces incompatibles — c'est le point). Divulgation obligatoire.
4. **Re-calibration conforme v11** : conformal_calibrate --pool v11 (alphas
   0.10/0.05, Mondrian >=12 lignes/strate sinon fallback poolé divulgué)
   => risk-scan-v11-conformal.json.
5. **Gate migration** : (a) conforme réalisé <= garanti sur lignes groundées ;
   (b) poison-style ext-LOAO sur pooled4 dans l'espace v11-jina reproduit
   0.7428 ± 0.01 (dérive d'implémentation interdite) ; (c) serving risk_scan
   live sur requêtes de contrôle (abstention/conformité du contrat v0.6.0).
6. **Déploiement** : ghost v0.6.0 (nouveau champ `encoder` + disclosure dans
   chaque réponse), drop-in pool-v11.conf sur le node, DRILL rollback complet
   dans les deux sens avant de déclarer servi.

## Interdits

Aucune ligne ajoutée/retirée/retouchée du pool pendant la migration (v10
append-only intouché) ; aucun seuil unixcoder réutilisé dans l'espace jina ;
le produit servi reste v0.5.1 (unixcoder) jusqu'à validation complète du
drill. La migration est réversible par design (drop-in).
