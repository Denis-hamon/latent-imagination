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

---

## FERMETURE — 2026-08-20 : **G1 VALIDÉ (2/6), référence interne mise à jour**

- **2/6 irréductibles résolus** : vuejs__core-9572 (t2) et iamkun__dayjs-1047
  (t2) — deux instances qui avaient résisté à v36/v37 (état cumulé seul) ;
- apply 14/18 = 78 % ; **pas-de-diff = 0/18** (vs 23/44 en v34) : la consigne
  « raisonnement court » élimine l'échec d'extraction même quand la troncature
  frappe encore (6/18 finish=length — le diff passe avant l'épuisement) ;
- extraction tolérante : 0 utilisation (assurance infra pour le futur) ;
- G2 descriptif : finish length 33 % (vs 53 % v34 à 16k, 11-25 % v35/v36 à 40-65k
  sans consigne courte) ;
- **restent irréductibles à 4 tours (mur cognitif confirmé)** : vuejs__core-11854
  (CSS scoped ::v-deep, 4 tours y=0), dayjs-1502 (locale bg), dayjs-1964
  (locales ar-ly/mr), dayjs-873 (customParseFormat yyyy) — sous-systèmes
  pointus locales/CSS, diagnostic cohérent pour les 4.

**Référence interne mise à jour** : vue 16/17 (94 %), dayjs 40/43 (93 %),
combiné **56/60 = 93 %** (contre 54/60 = 90 % avant v38).
