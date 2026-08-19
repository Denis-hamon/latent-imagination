# Fenêtre v28 — burst de collecte sur les 24 tickets vue MSWB + re-jugement

Suite close de v27 (24 tickets vue vérifiés RED→GREEN, patchs petits et
connus). Hypothèse : ces tickets produisent des réparations PARTIELLES non
triviales à taux plus élevé que les tickets agentiques durs (le fix réel est
petit et atteignable) — exactement ce qui désature la médiane Jaccard.

## Phase B1 — burst (≤192 appels, Pro + Qwen, ≤4 tours, mitigations DW-52)

Population : les 24 tickets mswb/vuejs__core/verified-mswb.json, tels quels.
Livraison : lignes replay-v28 appliquées (y, failed_all) intégrées au dataset.

Grille B1 scellée :
- G1 : taux d'application ≥ 35 % (v22/v25 = 31-33 % ; les patchs vue sont
  petits ⇒ attendu meilleur ; sinon la source n'apporte rien) ;
- G2 : ≥ 8 partielles NON triviales (red non vide ET au moins un déclaré
  réparé) ajoutées au dataset.
G1 ET G2 ⇒ Phase B2 ; sinon close.

## Phase B2 — re-jugement (grille v23 IDENTIQUE, zéro amendement)

Ré-entraînement recette 3896a3e7 (λ 1e-2) sur dataset complet étendu ;
M1 médiane Jaccard LOO-ligne ≥ B1 médiane + 0.05 ; M2 AUC paire ≥ 0.62 ;
M3 subset replay (v22+v25+v28) médiane ≥ B1 subset + 0.05.
Passage ⇒ poids v4 servis (v0.8.2, backup v3=v26, drill rollback, blackbox
live zed-hosted comparatif). Échec ⇒ close, données conservées.

## Interdits

Pas d'amendement de métrique (la médiane reste l'instrument de grille tant
qu'elle n'est pas saturée ; la saturation se mesure : si M1 ressort encore
1.0=1.0, c'est un RÉSULTAT, pas un bug à contourner).
