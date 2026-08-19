# Fenêtre v33 — boucle v32 avec solveurs compétents (owner : « A : meilleur solveur »)

Qwen3.8 testé KO à l'endpoint le 2026-08-19 (content=0, reasoning seul,
3e constat) : il ne peut PAS être le meilleur solveur actuellement malgré le
meilleur taux de convergence mesuré en v32. GLM-5.2 rétabli (fence propre au
test) + gemma-4-31B-it probe OK. Nemotron 0 % apply en v32, exclu.

## Protocole (mécanisme v32 inchangé — état cumulé + code courant réel)

Mêmes 17 instances vue vérifiées v27 ; modèles : DeepSeek-V4-Pro, GLM-5.2-NVFP4,
gemma-4-31B-it ; 4 tours max par (instance, modèle) ; cap 240 appels ;
feedback riche 1600 chars ; sélection IDENTIQUE à v32 (replay-selection-v32.json).

## Grille scellée

- R1 resolution rate ≥ 70 % (≥12/17, ≥1 modèle converge) ;
- R2 apply rate ≥ 45 % des tours appliqués ;
- R3 budget ≤ 240 appels.
Descriptif : progression vs v32 (11/17), contribution par modèle.
Réussite ⇒ resolution rate de référence interne = max(v32, v33) publié ;
données de tours versées au stock trajectoires. Échec ⇒ plafond solveurs
internes confirmé, la voie « meilleur solveur » exige un modèle hors-endpoint.

## Interdits

Pas de modification du mécanisme v32 (seuls les modèles changent) ; pas de
Qwen/Nemotron (KO mesurés) ; fenêtre auto-contenue (les runs Pro de v32 ne
sont pas réutilisés dans la grille — nouvelle exécution complète).

---

## FERMETURE — 2026-08-19 : R1 ÉCHEC (35 %), attribution causale établie

- Résolution **6/17 = 35 %** (R1 ≥70 % ÉCHEC) ; apply 64 % (R2 OK) ; 94 appels (R3 OK).
- Par modèle : Pro applique 92 % mais converge 3 ; GLM converge 5 mais
  n'applique que 33 % ; **gemma 0 % apply (0 tour utilisable)**.
- **v33 n'a résolu AUCUNE instance nouvelle** : ses 6 instances résolues sont
  un sous-ensemble exact des 11 de v32. Perte nette = 5 instances, toutes
  dues à l'absence de Qwen3.8.
- Attribution v32 : Qwen seul résolvait **6 instances que personne d'autre ne
  touche** ; GLM en a repêché 3, 3 restent hors de portée sans Qwen.

**Conclusion causale** : Qwen3.8-2.4T est le meilleur solveur TS mesuré dans
la flotte interne (9 convergences en v32 malgré 27 % d'apply — son échec est
l'extraction de fence, pas le raisonnement), et son KO endpoint (content=0,
vérifié 3 fois le 2026-08-19) coûte −5 instances à la résolution. La voie
« meilleur solveur » avec les modèles ACTUELS de l'endpoint est épuisée :
Pro/GLM/gemma/Nemotron ne compensent pas. Le levier n'est plus dans la boucle
ni dans la combinaison de modèles — il est dans le rétablissement de Qwen
côté serving (problème de génération : reasoning produit, content vide) ou
dans un modèle hors-endpoint de classe frontier.
