# Fenêtre v29 — re-jugement per-test n°3, grille v23 IDENTIQUE, population 303

La médiane Jaccard est désaturée par les données (triviales 45 % < 50 %,
123 non-triviales). Re-jugement du modèle per-test (recette 3896a3e7,
λ 1e-2) sur 303 lignes / 225 partielles / ~1700 paires. Zéro appel LLM.
Grille strictement identique v23/v24/v26 — AUCUN amendement.

- M1 : médiane Jaccard LOO-ligne partielles ≥ médiane B1 + 0.05 ;
- M2 : AUC paire LOO-ligne ≥ 0.62 ;
- M3 : subset replay (v22+v25+v28) médiane ≥ B1 subset + 0.05.
Passage ⇒ poids v4 servis (v0.8.2, backup v3=v26, drill rollback, blackbox
live zed-hosted). Échec ⇒ constat définitif : la médiane reste l'instrument,
et si elle échoue encore sur une population majoritairement non-triviale,
la question n'est plus la saturation mais la capacité du modèle.

---

## FERMETURE — 2026-08-18 : NON PROMOUVABLE (4e tour), campagne close

Mesure sur données corrigées (bug de normalisation des noms v28 : préfixes
TAP « N - » retirés des red_set, disclosure ; les 16 lignes vue étaient
invisibles du training avant correction) :

- M1 médiane : 1.0 = 1.0 sur 191 partielles entraînables (**55 % triviales** —
  le régime de collecte les reproduit structurellement, la désaturation
  dataset 45 % ne se transfère pas à la population entraînable) ;
- M2 AUC paire : 0.8747 ✓ (>0.62) mais EN BAISSE vs v26 (0.894) ;
- M3 médiane subset replay : saturée ;
- Youden J : 0.659 (v26 : 0.717) ; Brier isotonic 0.1335 (v26 : 0.116).

**Fait nouveau décisif : les lignes vue Multi-SWE-bench dégradent le modèle
poolé** (hétérogénéité des noms/géométries entre repos, 297 lignes mais
signal plus dispersé). Le scaling « plus de données hétérogènes » ne porte
plus la courbe — elle baisse.

Lecture de fin de campagne (v21→v29) :
1. le modèle v3 (v26, 273 lignes) servi depuis l'override DW-55 reste la
   meilleure configuration mesurée (blackbox live J 0.80 vs v2 0.54) ;
2. la grille médiane est incompatibile avec le régime de collecte — prouvé
   4 fois sur des populations 108→191 ; ce n'est plus un artefact de taille ;
3. les axes explorés sont épuisés : géométrie cd/goal (arcs v17-v20),
   fine-tuning encodeur (Yu, détruit à 155 lignes), scaling hétérogène
   (v29b, courbe descendante).

Aucun poids v4. Le serving reste v0.8.1/v3. La décision stratégique revient
à l'owner : accepter le plateau produit actuel, ou changer de paradigme
(exécution dans la boucle plutôt que prédiction — trajectoires agentiques
complètes, ou Multi-SWE-bench trajs déjà publiées).
