# Bras ARM — embedder-sweep HF code-spécialisés (pré-enregistrement)

Fait suite au bras embedder-swap-qwen3 CLOS (a0d799d4 : Qwen3-Embedding-8B
0.6273 < unixcoder 0.6739). Question owner : existe-t-il sur Hugging Face un
embeddeur qui batte unixcoder-base ?

## Sélection des candidats (audit licence+taille effectué 2026-08-17)

RETENUS (licence permissive vérifiée, tient sur Quadro RTX 5000 15 Go) :
1. **jinaai/jina-embeddings-v2-base-code** — Apache-2.0, ~137 M, 768-d,
   pooling last-token (convention de la carte modèle), 439k downloads.
2. **Salesforce/codet5p-110m-embedding** — BSD-3-Clause, ~110 M,
   pooling first-token (convention parallèle unixcoder CLS).

ÉCARTÉS à l'audit (jamais testés, exclus pour raison enregistrée) :
- Salesforce/SFR-Embedding-Code-400M_R : CC-BY-NC-4.0 (non commercial) ;
- jinaai/jina-code-embeddings-1.5b : CC-BY-NC-4.0 ;
- jinaai/jina-embeddings-v4 : licence non déclarée sur la carte (7.9 GB) ;
- voyageai/voyage-code-3 : licence non déclarée, gated (0 download public) ;
- microsoft/graphcodebert-base : MIT mais ancêtre direct d'unixcoder
  (hypothèse hiérarchique déjà couverte par la famille).

## Protocole gelé

MÊMES textes que l'arm qwen3 (state = problem[:1200]+f2p[:6], diff =
diff.patch, goal = zéro), population pooled2 (80 lignes, 61+/19-), MÊME
mesure (LOAO-F1 ext-only, AUC Mann-Whitney, bootstrap 2000 seed 20260816),
pooling = convention native de chaque modèle (documentée ci-dessus, aucun
choix après coup).

## Grille de décision scellée (contrôle des comparaisons multiples)

Avec n=80 lignes, seuls les effets larges sont détectables — grille en
conséquence :
- un candidat est PROMOUVABLE seulement si AUC >= 0.70 ET IC95 borne
  inférieure > 0.60 ET AUC > unixcoder ;
- sinon tous => bras CLOS, unixcoder-base confirmé définitivement comme
  encodeur du world model (DW-40 étendu) ;
- aucun re-test ni tuning (instruction pooling, dim, prefix) après coup :
  l'échec d'un variant tel-que-spécifié est un échec, point.

## Interdits & portée

Aucun mix d'espaces dans un pool servi ; le vainqueur éventuel ouvre un bras
de MIGRATION distinct (re-embedding pool v10 + re-calibration conforme +
gates 9.1), jamais une substitution silencieuse.
