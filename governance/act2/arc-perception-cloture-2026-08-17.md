# Clôture d'arc — levier perception/représentation (2026-08-17)

Synthèse décisionnelle après 5 bras scellés (tous pré-enregistrés avant
mesure, toutes grilles appliquées sans exception).

## Hiérarchie des encodeurs (mesurée, espaces incompatibles entre eux)

| encodeur | classe | meilleure AUC mesurée | population |
|---|---|---|---|
| jina-v2-base-code (137 M) | code-spé | **0.7428** [0.640,0.840] | pooled4 (113) ; 0.6946 sur pooled7 (585) |
| unixcoder-base (125 M) | code-spé | 0.7217 [0.652,0.788] | pooled5 (219) |
| Qwen3-Embedding-0.6B | généraliste | 0.6560 [0.610,0.700] | pooled7 (585) |
| Qwen3-Embedding-8B | généraliste | 0.6273 [0.488,0.761] | pooled2 (80) |
| codet5p-110m | code-spé petit | 0.6721 (≈unixcoder) | pooled2 |

**Loi empirique dégagée** : la spécialisation code bat la taille ; la
famille Qwen3-Embedding généraliste perd à toutes les tailles testées.

## Métrique (bras mondrian 80fd6523)

AUC stratifiée pondérée (familles n>=12) = 0.5645 vs globale 0.6946
(delta −0.13). Le signal global provient des différences ENTRE familles ;
l'intra-famille est quasi-aléatoire (zod 0.40, lite 0.38, real 0.59).
La métrique globale LOAO-F1 était la mesure honnête — pas un artefact.

## Conclusion d'arc

Sous supervision binaire (y = le patch passe/échoue), la perception et la
métrique sont au plafond mesurable : ~0.69-0.75 selon population. Les
leviers restants changent de nature :
1. **Supervision plus riche** : prédire QUELS tests échouent (per-test), pas
   seulement si « ça passe » — nos run-results contiennent déjà les listes
   F2P nommées par test ; le dataset per-test existe déjà, la métrique reste
   à inventer (c'est le front P2).
2. **Produit d'abord** : Ghost v0.7.1 compense déjà le plafond par design
   (bootstrap réel n>=8, recommandation = mesure, abstention sinon) — validé
   par deux agents réels sur ticket réel (#9436).

Aucun de ces constats ne retire de valeur au pool servi : pooled7 (585 lignes
groundées) est le jeu de données TS le plus riche du projet, archivé pour
toute expérience future (per-test, fine-tuning d'encodeur sur nos issues, etc.).
