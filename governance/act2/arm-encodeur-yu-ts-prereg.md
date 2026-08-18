# Bras ARM — architecture : fine-tuning encodeur par supervision dense per-test
(Yu-Thm1 appliqué à TS, propriétaire « ok go ! », lignée DW-54/v23)

Thèse testée : le plafond TS est représentationnel — l'encodeur gelé range
par identité de tâche, pas par effet du patch sur les tests. Fine-tuner le
trunk (LoRA 2 derniers blocs) avec un objectif AUXILIAIRE DENSE multi-hot
per-test doit déformer l'espace pour que la géométrie porte le signal
intra-ticket sans la béquille de concaténation manuelle.

## Population (figée : v23-model-input)

155 lignes / 1066 paires / vocabulaire 199 noms de tests déclaré. LOAO par
TÂCHE (139 tâches) — jamais la tâche held-out dans le fine-tuning du fold.

## Protocole gelé (hérite Yu + parité serving)

- encodeur : jina-v2-base-code ; pooling last-token natif ; max_length 2048
  tok (troncature figée bras — parité entre bras gelé et bras tuné, budget
  GPU 16 Go ; disclosure vs 8192 serving) ;
- LoRA r=8 α=16 sur query+value des 2 derniers blocs, trunk gelé ;
- tête auxiliaire : 199 sorties multi-hot (1 = test encore rouge), masquée
  hors declared de la ligne ; loss BCE ; témoin binaire y (tout déclaré
  réparé) entraîné SÉPARÉMENT, jamais lu par l'auxiliaire ;
- folds : LoAO tâche ; 20 epochs max, early-stop loss train (graine 6769) ;
- features paire = [E_diff‖E_test‖cos] avec l'encodeur du fold ; logistique
  L2 λ=1e-2 identique v23 sur les paires train ; prédictions sur held-out.
- BASELINE interne : même pipeline mot à mot avec l'encodeur GELÉ (pas de
  référence croisée à v23 — comparabilité stricte dans le même protocole).

## Grille scellée (3 conditions, toutes requises)

- **F1 paire** : AUC LOAO du bras tuné ≥ AUC LOAO gelé (même protocole) + 0.02 ;
- **F2 Jaccard moyenne** (métrique non saturée, 108 partielles, seuil Youden
  du bras) : moyenne tunée ≥ moyenne gelée + 0.05 ;
- **F3 thèse Yu (géométrie seule)** : AUC binaire LOAO-f1 sur cd=E_state+E_diff
  (states reconstruits depuis les sources) : tuné ≥ gelé + 0.05 — c'est la
  mesure du remaniement représentationnel SANS tête per-test.
Échec d'une seule ⇒ bras CLOS (la thèse Yu est fausse à cette échelle de
données ; le modèle v2 reste servi). Réussite ⇒ fenêtre de promotion
séparée (swap d'encodeur de la tête per-test + recalibration, décision owner).

## Interdits

Pas d'augmentation de la population en cours de bras ; pas de choix de
seed/epochs post-hoc ; le serving reste v0.8.0 modèle v2 pendant tout le bras.
