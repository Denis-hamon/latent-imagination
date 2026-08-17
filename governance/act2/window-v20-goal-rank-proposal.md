# Fenêtre v20 — axe goal en RANKING comparatif, sans verdict (owner « go » piste a)

Leçon v19 scellée : l'axe goal CLASSE (AUC 0.7495) mais ne SÉPARE pas à seuil
unique (J 0.44). La piste (a) sert exactement ce que le signal sait faire :
ORDONNER des candidats, jamais décider. Produit : section `goal_rank`
additive dans compare_patches, activée seulement si l'appelant passe
`goal_text`. risk_scan / assess_patch / pool v12 : rien ne change.

## Intégration (zéro appel LLM, zéro drop-in)

- `goal_rank` : pour chaque candidat, énergie goal `1−<E_state+E_diff,
  E_state+E_goal>` (formule energy_of exacte ; diff[:8000], goal[:8000] =
  parité population v18 ; state tel que fourni) ; retour = ordre croissant
  d'énergie + énergies brutes + disclosure « classement sans verdict, aucun
  seuil » ; pas de predicted_red, pas de advice.
- Absence de goal_text ⇒ section absente (pas d'abstention inventée).

## Grille scellée (avant mesure)

- **R1 intra-ticket** (la métrique produit réelle : des candidats du MÊME
  ticket comparés entre eux) : précision par paire sur les paires (y=0, y=1)
  de même ticket dans v18 ≥ 0.60, avec ≥ 150 paires, IC95 bootstrap ≥ 0.55 ;
- **R2 blackbox LIVE** sur un ticket réel à classes mixtes : l'ordre retourné
  par le serveur place le(s) y=1 avant le(s) y=0 (direction correcte) ;
- **R3** : sans goal_text, réponse compare_patches bit-compatible avec la
  v0.8.1 servie (section absente ; phase/reco inchangées) + suite de tests verte.
R1+R2+R3 requis pour servir goal_rank ; échec ⇒ pas d'intégration, leçon
consignée (le ranking intra-ticket serait lui aussi mort).

## Interdits

Aucun seuil dans goal_rank, même « informatif » ; aucune calibration servie ;
pas de pool v18 chargé par le serveur (l'énergie est query-only) ; le nom
même de « prédiction » évité dans la réponse (c'est un ordre).

---

## FERMETURE — 2026-08-17 : **R1 ÉCHEC, rien n'est servi, piste (a) RÉFUTÉE**

- **R1 intra-ticket** : acc paire 0.4198 (< 0.50 : PIRE QUE LE HASARD),
  n = 131 paires (< 150), IC95 [0.309, 0.473]. 18 tickets à paires mixtes.
- R2/R3 non joués (la grille exige R1 d'abord — discipline, pas d'économie).

Lecture (la plus importante de la série TS) : l'AUC 0.7495 de v18 était
porté par les paires **inter-tickets** (fix du ticket A contre patch raté du
ticket B — paire facile). Dans le cas d'usage produit réel — ordonner des
candidats du MÊME ticket — l'axe goal classe à l'envers (0.42). La grille
intra-ticket a été exactly ce qui a tué le mirage : elle mesure le produit,
pas la statistique. La piste (b) avait ce signal depuis v15 : le modèle
per-test (E_diff × E_test) est bon intra-tâche (Jaccard LOO 0.83), parce
qu'il a les NOMS de tests — l'axe goal seul ne les a pas.

Conséquences :
1. goal_rank n'est pas intégré (zéro code serveur modifié, zéro serving) ;
2. le ranking intra-ticket TS existe DÉJÀ côté produit : c'est la colonne
   per-test servie en v0.8.0 (somme des P(rouge) par candidat = ordre) ;
3. pistes restantes pour TS : (b) fenêtre conjointe goal+per-test, ou
   (c) plafond accepté ; l'accumulation passive continue via flywheel.
Artifact : arm-v20-goal-rank-R1-2026-08-17.json.
