# Fenêtre v42 — PRODUIT : colonne « évolution prédite des tests » (owner : « pré-enregistre et lance »)

Arm transition VALIDÉ deux fois (v39 1ffa1fff, v41 6928f0ab : AUC 0.993,
Jaccard 0.933 vs persistance 0.820/0.78). Produit : après une exécution
réelle partielle, l'appelant passe l'état rouge COURANT + les candidats ;
Ghost prédit par test « restera rouge après ce patch », SANS exécuter.

## Intégration (additive, serving v0.8.2)

- nouvel env `LI_TRANSITION_MODEL` (transition-model.npz : poids logistiques
  1540-dims [E_diff‖E_test‖cos‖persist‖frac‖tour] + seuil Youden + isotonic
  PAV) ; absent ⇒ section jamais émise (comportement v0.8.1 bit-identique) ;
- `compare_patches(..., known_red_tests=[...])` : section `predicted_evolution`
  par candidat ; SANS known_red_tests ⇒ ABSTENTION de la section (le modèle
  n'est jamais utilisé hors de son régime séquentiel — règle P4) ;
- chemin binaire, risk_scan, pool v12, per-test v3 : RIEN ne change.

## Grille scellée

- **P1 reproduction** : entraînement final sur 747 paires + LOO reproduit
  AUC ≥ 0.97 (v41 = 0.9931 ; marge contre l'entraînement plein) ;
- **P2 intégrité** : chemin binaire intouché (preuve diff) + gate 9.1
  acc@10 rerun 0.907 ± 0.001 ;
- **P3 blackbox live** : ≥ 5 transitions réelles archivées rejouées via le
  serveur (red_t connu + diff_{t+1} + vérité red_{t+1}) ; pour ≥ 70 % des
  paires (test resté rouge, test réparé) d'une même transition : p(rester
  rouge) du rouge > p du réparé ;
- **P4 abstention** : sans known_red_tests, réponse v0.8.2 strictement égale
  à v0.8.1 sur les sections existantes + section évolution absente.
P1+P2+P3+P4 requis. Échec ⇒ pas de serving v0.8.2, poids non servis.

## Interdits

Pas de réutilisation du modèle hors régime séquentiel (known_red absent ⇒
abstention, pas de repli sur le modèle one-shot pour cette colonne — le
one-shot a SA colonne distincte, déjà servie) ; pas de recalibration
post-blackbox.

---

## FERMETURE — 2026-08-21 : **GRILLE 4/4 — Ghost v0.8.2 SERVI**

- **P1** : LOO (folds = trajectoires uniques, 180 replis ≡ transitions car
  aucune trajectoire partagée) AUC **0.9931** ≥ 0.97 ✓ ; Jaccard LOO 0.9333 ;
  Youden J 0.9665, seuil 0.019 (classe rare 30/747, disclosure) ; poids
  exportés transition-model.npz (1540 dims + isotonic PAV) ;
- **P2** : acc@10 régime servi rerun **0.907** exact ; diff ghost_server.py
  strictement additif (+88/−4, energy_of/pool/calibrations intouchés) ;
- **P3 blackbox LIVE** : 6 transitions réelles rejouées via le serveur,
  **15/15 paires (rouge-réel, réparé) correctement ordonnées (100 % ≥ 70 %)** ;
  2 cas à known_red vide → abstention correcte (section absente) ;
- **P4** : réponse sans known_red_tests BIT-IDENTIQUE à v0.8.1 (snapshot
  comparé) ; section predicted_evolution absente ✓.

Serving : drop-in enrichi (LI_TRANSITION_MODEL), version 0.8.2, rollback =
retrait de la ligne env (comportement redevient v0.8.1 bit-identique, prouvé
par P4). Disclosure classe rare : 30 labels rouges inchangés depuis v39 ;
l'AUC 0.99 porte surtout sur des négatifs enrichis — le produit est un
signal advisory, pas un verdict (contrat affiché dans la réponse serveur).

**Première capacité séquentielle servie du world model** : Ghost prédit
désormais l'effet d'un patch SACHANT l'état mesuré courant — exactement le
régime d'un agent qui itère.
