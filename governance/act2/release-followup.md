# Fenêtre de publication 2026-08-07 — journal

## Exécuté dans cette fenêtre

| item | statut | preuve |
|---|---|---|
| Budget R10 Act II pré-enregistré (avant tout spend) | ✅ | `governance/act2/budget-v1.toml` |
| HF Hub mirror (test avec vrai token) | ✅ | https://huggingface.co/datasets/denishamon/latent-imagination-releases (29 fichiers) |
| HF README card (metadata citable) | ✅ | poussé via HfApi |
| Distribution block corpus-release v0 mis à jour | ✅ | `data/store/canonical/corpus-release-v0/v0/corpus-release.json` |
| Pilote Kimi-K3 (1 appel borné sur budget) | ✅ | `governance/act2/family3-pilot/` — 1/2000 calls, false start honnête |
| verify_offline OTS parse (deferred Epic-1 M-1) | ✅ | `packages/prereg/tests/test_verify.py` sur la vraie preuve |

## Non exécuté — tokens manquants (à fermer par l'humain)

- **DOI Zenodo** : l'adapter est prêt et testé ; exécution = fournir `LI_ZENODO_TOKEN`
  et lancer `scripts/prereg/release_ceremony.py --packets-gneration…` — je te tends le
  guide quand tu l'as.

## Reste post-fenêtre (discipline)

- Rotation des tokens HF collés dans la conversation (les deux, `denishamon`).
- Act II campagne complète (Kimi/GLM/Qwen ≥ 50 calls) — attendue fenêtre node dédiée.
- Spot-audit docker-verified 1 % du Clean Tier (tasks 72) — même fenêtre.
