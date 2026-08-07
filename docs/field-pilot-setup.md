# Field pilot — installer l'advisory gate chez soi (Kenji, 15 min)

Objectif : chaque patch émis par l'agent est annoté AVANT exécution, sur ta machine,
sans rien envoyer à personne (zero-custody : tout atterrit dans TON dossier).

## 1. Installer

```bash
git clone https://github.com/Denis-hamon/latent-imagination
cd latent-imagination
uv sync --locked --all-packages          # deps figées, aucune dépendance ML/LLM requise
```

## 2. Positionner le snapshot pinné

Le gate ne lit JAMAIS un store vivant — il charge une COPIE épinglée :

```bash
mkdir -p ~/.latent-imagination/snapshot
# Le snapshot pinné ship dans le repo (posture branche iii, divulguée) :
cp demo/gate-advisory/fixtures/predictor.json demo/gate-advisory/fixtures/META.json \
   ~/.latent-imagination/snapshot/
sha256sum ~/.latent-imagination/snapshot/predictor.json   # note le hash
```

## 3. Environnement (LI_* exclusivement)

```bash
export LI_GATE_SNAPSHOT=~/.latent-imagination/snapshot
export LI_GATE_PREDICTOR_SHA256=<le hash ci-dessus>   # refus au démarrage si mauvais
export LI_GATE_LOG=~/.latent-imagination/decisions.jsonl
export LI_GATE_TEST_SELECTION="tests/"   # optionnel: ta sélection désignée (OQ-10 tier 2)
```

## 4. Brancher le hook (Claude Code, surface documentée PreToolUse)

Dans `~/.claude/settings.json` :

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {"type": "command",
           "command": "cd <repo>/latent-imagination && uv run python -m gate_adapters.claude_code_hooks"}
        ]
      }
    ]
  }
}
```

Le hook ne bloque JAMAIS (advisory-only, par construction — il n'existe pas de chemin
dans le package qui puisse stopper ton outil). Une annotation apparaît comme
`systemMessage` (toi) + `additionalContext` (l'agent). Si le gate est mal installé,
tu vois UNE ligne d'installation et tout continue.

## 5. Inspecter ta télémétrie (local, à toi)

```bash
uv run python -m gate_adapters.telemetry_etl ~/.latent-imagination/decisions.jsonl
```

## 6. Dépendre de la confidentialité

Tout est local. Les skins/thèmes/patches ne quittent pas ta machine. La seule écriture
est le log JSONL ci-dessus. Pour démonter : supprimer le bloc hooks + `~/.latent-imagination/`.

<details><summary>Notes de posture (posture sub-barre, verdict branche iii)</summary>

Le predictor embarqué est la baseline mesurée Epic 3 (précision 0.6271 en matched control,
SOUS la barre enregistrée 0.8889). Le gate est en mode advisory-scaffold : les annotations
portent cette mesure dans chaque payload (`predictor_disclosure`). C'est le chemin de
collecte pour le prochain cycle — pas un produit certifié.
</details>
