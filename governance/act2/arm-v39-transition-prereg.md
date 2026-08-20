# Bras ARM v39 — modèle de transition séquentielle (paradigme 1, suite 3)

Idée (inédite dans la campagne) : la réparation agentique est un PROCESSUS —
chaque tour produit (diff_t, red_set_t). Prédire red_set_{t+1} à partir de
(diff_{t+1}, red_set_t) au lieu de red_set depuis diff seul. Le signal
séquentiel (« ce test était rouge au tour précédent et le diff ne le touche
pas ») est absent des modèles one-shot (v23-v31).

## Population figée

Toutes les transitions (t → t+1 appliqués consecutifs, même instance+modèle)
des fenêtres v32→v38 à la date de construction : au décompte pré-arm,
39 trajectoires / 74 transitions / 39 avec changement de red-set.
Paires = (transition, test déclaré) → label = test ∈ red_{t+1}.

## Protocole gelé

- features par paire : [E_diff_{t+1} (768) ‖ E_test (768) ‖ cos (1) ‖
  persist (1 : test rouge en t) ‖ frac_rouges_t (1) ‖ tour (1)] = 1534 dims ;
  embeddings jina protocole servi (diff tronqué 8000 chars) ;
- modèle : logistique L2 λ=1e-2 (LBFGS), LOO par TRAJECTOIRE entière (toutes
  les transitions d'une (instance, modèle) sortent ensemble) ;
- baseline PERSISTANCE : prédiction red_{t+1} = red_t (la feature seule) —
  mesurée par le même pipeline avec features réduites à [persist].

## Grille scellée

- T1 : AUC paire LOO-trajectoire du modèle complet ≥ AUC persistance + 0.03 ;
- T2 : Jaccard moyen (sur transitions à red-set non vide en t+1, seuil Youden
  du modèle) ≥ Jaccard persistance + 0.05 ;
- T1 ET T2 ⇒ le signal séquentiel existe ; ouvre une fenêtre produit
  (colonne « évolution prédite des tests ») — décision owner. Sinon CLOS :
  la persistance suffit, le paradigme séquentiel n'apporte rien de mesurable.

## Interdits

Aucune feature post-hoc au-delà des 6 gelées ; pas de sélection de
sous-population ; le serving v0.8.1 reste intouché.
