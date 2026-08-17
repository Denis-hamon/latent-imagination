# Exploration P2.0 — supervision per-test (2026-08-17, zéro appel)

Fait suite à la clôture de l'arc perception (54f79ad) : le prochain front
identifié est la supervision plus riche — prédire QUELS tests échouent, pas
seulement « ça passe ou pas ».

## Audit des données EXISTANTES

- 201/205 run-results conservent des issues nommés par test (tails texte
  complets v6+ ; v2-v5 partiels) ⇒ le dataset per-test est récupérable sans
  ré-exécution.
- **41 réparations partielles** (f2p_rc=1) avec tests-encore-rouges nommés ;
  10 tâches >= 2 partiels ; **4 tâches à patterns d'échec diversifiés** :
  - omniroute__lite.triple_coordinated : 5 patches, **3 patterns distincts**
  - zod__str.ulid_and_nanoid : 4 patches, 2 patterns
  - omniroute__usage.buffer_leaks : 2/2 ; date_fns__bizdays.double_weekend : 2/2
  Les 6 autres tâches : échec partiel STRUCTURÉ (tous les auteurs ratent la
  même région — la région la plus dure) ⇒ signal prédictif potentiel mais
  dégénéré en variété.

## Lecture

Le signal per-test EXISTE (patterns cohérents et diversité là où les triples
ont été multi-tirages), mais le volume est insuffisant pour un bras de
modélisation : 41 lignes. Il faut une collecte DÉDIÉE per-test :
1. label exec capturant l'issue COMPLET par test (pas de troncature de tail) ;
2. collecte ciblée triples/hard sur tâches à haut F2P avec >= 5 tirages
   (Flash sur triples = pourvoyeur prouvé) pour multiplier les partiels par
   tâche ;
3. métrique P2 à concevoir : exactitude de l'ensemble-rouge prédit (Jaccard
   patch-voisinage), jamais de label deviné.

## Proposition v15 (NON ratifiée — décision owner)

Fenêtre COVERAGE-TS-v15 « per-test » : ~150-250 appels Flash sur 15-20 tâches
triples/hard à >=4 F2P (OmniRoute prioritaire, familles denses), label exec
étendu full-outcomes, constitution dataset per-test >= 150 lignes partielles,
puis bras de mesure P2 pré-enregistré. Serving Ghost inchangé pendant tout
l'arc (le produit v0.7.1 vit sur la supervision binaire qui reste valide).
