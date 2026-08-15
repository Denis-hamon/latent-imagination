# GHOST MCP

**Le fantôme de chaque run passé note votre brouillon de patch.**

GHOST est un world-model servi en MCP : il compare votre diff candidat à la
géométrie des issues passées (attracteur d'échecs, goal-free — aucun gold
requis) et prédit l'issue AVANT que vous n'investissiez une exécution.
Il ne prédit que dans un régime mesuré à **acc ≥ 0.95** (10 % de couverture,
LOAO, pool v8 n=207) ; sinon il répond `abstain` — le fantôme se tait quand
il ne sait pas. **Advisory only** : rien ne remplace l'exécution des tests.

## Installation — client distant (recommandé, à la Context7)

Le serveur tourne sur le node GPU (poids unixcoder + pool). Une URL suffit.

Optionnel mais recommandé — résolvez `ghost-mcp` en local (alias SSH déjà
posé ; cette ligne rend l'URL utilisable par les clients HTTP) :

```sh
echo "51.210.228.117 ghost-mcp" | sudo tee -a /etc/hosts
```

**Claude Code** (une ligne) :

```sh
claude mcp add --transport http ghost http://ghost-mcp:8093/mcp
# sans l'entrée hosts :
claude mcp add --transport http ghost http://51.210.228.117:8093/mcp
```

**opencode / Cursor / tout client `mcpServers`** :

```json
{
  "mcpServers": {
    "ghost": {
      "url": "http://ghost-mcp:8093/mcp"
    }
  }
}
```

## Installation — stdio local (colocalisé, sans réseau)

```json
{
  "mcpServers": {
    "ghost": {
      "command": "/path/to/latent-imagination/.venv/bin/python",
      "args": ["/path/to/latent-imagination/scripts/mcp/ghost_server.py"]
    }
  }
}
```

(Le venv doit contenir torch + transformers ; le modèle unixcoder-base et le
pool v8 sont attendus aux chemins par défaut `data/landing/act2-pilot/`.)

## Utilisation — le contrat en 4 temps

1. **`preflight_patch(repo_path, diff_text)`** — contrôles déterministes
   gratuits (git-apply, py_compile). À lancer avant tout le reste.
2. **`risk_scan(state_text, diff_text, reporter, exclude_task?)`** — le score
   du world model. Passez `reporter` = votre identité de LLM/agent, et
   `exclude_task` si la tâche en cours est dans le pool (anti-fuite). Le
   `call_id` renvoyé sert à l'étape 4.
3. Faites tourner les vrais tests.
4. **`report_outcome(call_id, passed, reporter, grounded_by)`** — renvoyez
   l'issue **groundée** (méthode de mesure : `pytest-f2p`, `ci`, `human`…).
   Les issues auto-déclarées sans méthode sont rejetées du renforcement.
   Chaque issue groundée alimente le flywheel (collecteur nocturne
   `scripts/act2/mcp_flywheel.py`).

Lecture des verdicts `risk_scan` :
- `low_risk` / `high_risk` + `expected_acc_regime` : verdict dans la zone
  calibrée (acc mesurée 0.952, Wilson [0.773, 0.992]) ;
- `abstain` : confiance insuffisante — décidez par vos tests, pas par GHOST.

Autres tools : `near_mis_patches` (k plus proches issues réelles, pour
informer un choix), `assess_patch` (axe GOLD, mode harness seulement —
nécessite le texte du but, indisponible en production).

## Ops (node)

```sh
# démarrage (déjà actif si installé par le run 2026-08-15)
cd ~/latent-imagination/scripts/mcp && \
  nohup ../../.venv/bin/python ghost_http_server.py > /tmp/ghost-http.log 2>&1 &
# arrêt
pkill -f ghost_http_server.py
# env : GHOST_HOST (défaut 0.0.0.0), GHOST_PORT (défaut 8093), GHOST_TOKEN (cf. Sécurité)
```

Sécurité (durcissement 2026-08-15) :
- **Auth** : `GHOST_TOKEN` posé dans l'env du service → le serveur exige
  `Authorization: Bearer <token>` (constant-time, fail-closed : si la lib ne
  supporte pas `token_verifier`, le serveur REFUSE de démarrer plutôt que
  servir « protégé » en nom seul). Sans token : avertissement au démarrage,
  réseau interne uniquement.
- **Provenance du pool servi** : `governance/act2/arm-artifacts/pool-v8-provenance.json`
  (sha256 des fichiers servis, lignée v7→v8, mesures au gel). À ancrer dans le
  prereg ledger à la prochaine cérémonie.
- **Backup WORM** : les pools + calibrations sont la matière première du world
  model ; sur le node, miroiter vers le bucket objet avec object-lock :
  `mc mirror --overwrite ~/latent-imagination/data/landing/act2-pilot/ \
     minio/latent-imagination-artifacts/act2-pilot/ && \
     mc retention set --default GOVERNANCE 365d minio/latent-imagination-artifacts/act2-pilot`
  (bucket dédié, PAS le bucket de releases ; procédure owner, fenêtre cérémonie).
- Pool/calibration servis : `latent-pool-v8.json/.npz` +
  `risk-scan-v8-calibration.json` (chemins surchargeables `LI_POOL_JSON`/
  `LI_POOL_NPZ`). Version serveur : `ghost` 0.4.0.

## Honnêteté mesurée (addendum 2026-08-15)

| instrument servi | AUC | régime fiable |
|---|---|---|
| risk_scan (world model goal-free) | 0.615–0.675 global | acc 0.952 [0.773,0.992] sur les 10 % où il répond |
| le reste du temps | — | `abstain` |

Le flywheel (report_outcome → mcp_flywheel.py → pool v9) est l'axe
d'amélioration : plus d'issues groundées = plus de couverture fiable.

## v0.4.0 — familles et abstention expliquée (2026-08-15)

- `family` = dérivation MÉCANIQUE du préfixe de tâche (`owner__repo`), zéro
  modèle. Chaque réponse `risk_scan` porte un bloc `family` additif :
  famille la plus proche (similarité cosinus en espace d'état), sa couverture
  dans le pool (n / positives / négatives), top-5 familles, nombre total de
  familles du pool.
- Les abstentions portent `abstention_diagnosis` : « hors régime fiable ;
  famille la plus proche X (n lignes, p positives) — pas assez de masse ici
  pour trancher à acc ≥ 0.95 ». La DÉCISION (attracteur + tau) est inchangée :
  le diagnostic est additif, jamais un aiguillage du score.
- `reporter` manquant = accepté mais signalé (`reporter_note` dans la réponse,
  `reporter_missing: true` dans le log) : sans identité d'auteur, la paire ne
  peut pas être stratifiée par le flywheel (contrat multi-LLM).
- `near_mis_patches` renvoie désormais `family` par voisin.
- Tests hors-ligne (numpy seul, embed mocké — pas de torch) :
  `scripts/mcp/test_ghost_server_family.py` ; skippent proprement quand le
  pool v8 est absent (CI propre).

Design note (mesuré, pas spéculé) : les familles servent d'abord à EXPLIQUER
l'abstention et à CIBLER la croissance du pool. Le routage du score par
famille est un pari non mesuré (sous-pools trop petits pour tenir le régime
acc ≥ 0.95 chacun) — il reste hors service tant qu'une éval family-LOAO
pré-enregistrée ne montre pas le contraire. Séparation maintenue : GHOST
reste goal-free et sans LLM dans la boucle de décision.
