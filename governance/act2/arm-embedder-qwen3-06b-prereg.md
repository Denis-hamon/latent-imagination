# Bras ARM — 3e encodeur : Qwen3-Embedding-0.6B sur pooled7 (pré-enregistrement)

Motivation : plateau géométrique confirmé (bras mondrian 80fd6523 : delta
stratifié −0.13). Le levier représentation est le dernier bras de la famille
« perception » : unixcoder-base (code-spé 0.13B) 0.6634-0.6951 ; jina-v2-code
(code-spé 0.14B) 0.7230-0.7428 selon population ; Qwen3-Embedding-8B
(généraliste) 0.6273 (pire). Qwen3-Embedding-0.6B (Apache-2.0, 1.2 GB) teste
la famille Qwen3 à taille réduite — si lui aussi perd, la conclusion de
clôture s'impose : la hiérarchie des encodeurs est plate au-delà du code-spé
137M, le plafond est la supervision binaire elle-même.

## Protocole gelé

- Population : pooled7 (585 lignes, 313+/272-) — textes identiques
  (state=problem[:1200]+f2p, diff=diff.patch[:6000 tronqué], goal=0) ;
- chargement local GPU node, pooling last-token natif Qwen3-Embedding,
  max_length 8192 ; aucune instruction-prefix (comparaison contrôlée) ;
- mesure : LOAO-F1 ext-only, AUC Mann-Whitney, bootstrap 2500 seed 20260816 ;
- contrôle jina recalculé même run (attendu 0.6946 ± 0.001).

## Grille de décision scellée

- Qwen3-0.6B : AUC >= 0.72 ET IC95 lo >= 0.70 ET > jina => PROMOUVABLE
  (bras de migration distinct, cérémonie standard) ;
- sinon => CLOS ; clôture cumulative de famille journalisée (le levier
  perception est épuisé sur supervision binaire — pivot supervision plus
  riche : prédiction per-test, ou acceptation du plafond au bénéfice du
  produit qui calibre déjà par session).
