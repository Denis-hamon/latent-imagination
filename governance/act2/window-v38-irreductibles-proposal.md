# Fenêtre v38 — traitement des 6 irréductibles + robustification extraction

Diagnostic v36/v37 sur les 6 irréductibles (vue 11854, 9572 ; dayjs 1047,
1502, 1964, 873) : (A) ~35 % des tours Qwen tronqués même à 65536 tokens
(finish_reason=length, fences coupées, réponses raw non conservées donc
irrécupérables) ; (B) mur cognitif sur sous-systèmes pointus (CSS scoped
::v-deep, locales dayjs, customParseFormat) — mêmes tests rouges sur 3-4
tours ; (C) pièges d'état cumulé (« file exists » non corrigés).

## Protocole gelé

1. **Infra (zéro mesure)** : sauvegarde des réponses raw par tour
   (t{N}.raw) ; extraction TOLÉRANTE si la fence finale manque (diff depuis
   le dernier « diff --git » jusqu'à EOF si celui-ci contient des hunks
   complets) — appliquée aux fenêtres futures, pas de re-mesure rétroactive ;
2. **E2 ciblé** : rejouer les 6 instances avec prompt « raisonnement < 5000
   tokens puis diff » (mitigation troncature par consigne, pas par budget),
   Qwen 65536, ≤4 tours, état cumulé identique. Cap 24 appels.

## Grille scellée

- G1 : ≥ 2/6 instances résolues ⇒ la mitigation pensée-courte débloque une
  partie du mur ; <2 ⇒ le mur est COGNITIF à 4 tours sur ces sous-systèmes,
  le constat est définitif pour ce bloc et la recette 90 % reste la référence ;
- G2 descriptif : taux finish_reason=length avec la consigne vs 35 % mesuré.
Aucune modification de la référence interne (v36/v37 restent les scores).
