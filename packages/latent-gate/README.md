# Latent Gate — service public (v1)

Service MCP/HTTP du modèle-consequence latent-imagination. **Rosetta** : le score
est calculé par la recette mesurée du projet (énergie latente GOLD × attracteur
d'échecs, combinée logreg λ=1, abstention par quantiles de confiance LOAO).
Le pool et les poids calibrés sont des **artefacts hors-git, hashés** (la sauce) ;
l'instrument de mesure (eval pack frozen32 + `exclude_task`) est public.

Layout :

- `src/latent_gate/` — la lib + les deux serveurs (stdio MCP, HTTP FastAPI)
- `tests/` — tests unitaires (CPU, sans GPU)
- `public/` — tout ce qui est destiné au dehors : README, Dockerfile, eval pack
- `public/artifacts/` — NON commité : latent-pool-v6.npz/.json, model.json (calibré)

Règles dures : le diff se score **tel qu'émis** (jamais après sanitize) ;
l'abstention est une réponse de première classe ; `report_outcome` ne mute
jamais le pool en ligne.
