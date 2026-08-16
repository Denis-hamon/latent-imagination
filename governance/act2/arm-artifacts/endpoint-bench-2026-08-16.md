# Benchmark endpoint /galere — 2026-08-16 (12 appels journalisés coverage-bench-author)

Contexte : question owner « pourquoi ne pas passer par les autres modèles servis
(/galere) pour le levier throughput ? ». Réponse par la mesure, pas l'opinion.

## Mesure (prompt court, max_tokens 4000, 3 appels/modèle en concurrence)

| modèle | latences (s) | diff fence | note |
|---|---|---|---|
| DeepSeek-V4-Flash | 0.6 / 0.6 / 0.7 | 3/3 | ~100× plus rapide que l'auteur épinglé |
| Qwen3.8-2.4T-A95B-NVFP4 | 9.7 / 8.1 / 6.0 | 3/3 | ~10× |
| GLM-5.2-NVFP4 | 16.9 / 28.8 / 33.5 | 3/3 | ~3× |
| MLX-Qwen3.5-35B-A3B-…-bf16 (ÉPINGLÉ) | 11.9 / 83.1 / 91.5 | 3/3 | baseline |

11 modèles servis au total (Nemotron-3-Super-120B, DeepSeek-V4-Pro, gemma-4
26B/31B, Bielik-11B, Muse-Glimmer-30B, les deux DeepSeek-V4-Flash…).

## Lecture honnête

1. **Le levier throughput multi-modèles EXISTE** : fan-out sur 3-4 backends
   rapides = potentiel x10-x30 sur le volume de lignes/jour, sans aucune
   infra à monter (contrairement au plan vLLM local initial).
2. **MAIS** : la latence benchmark ne dit rien de la CAPACITÉ à produire des
   diffs applicables sur nos tâches complètes (prompt court ici ; fichier
   complet + classe prompt gelée en fenêtre). Chaque nouveau modèle-auteur
   doit passer la SONDE de fenêtre (≥1 tirage applicable sur 2) avant tout
   quota — discipline identique aux nouveaux fichiers v6/v7.
3. **Provenance** : les lignes issues d'un autre auteur = population À PART
   (tag author), mesurée par les MÊMES gates scellées (poison ext-LOAO ≥0.65,
   classes ≥5) avant tout mix. La comparabilité d'échelle est assurée par le
   contrôle v6/v9 (même métrique).
4. **L'auteur épinglé RESTE le baseline** : v6-GOLD et toute la calibration
   conforme v0.5.1 sont assises sur son lignage ; on n'y touche pas, on
   AJOUTE des populations.

## Proposition v8 (non ratifiée — décision owner)

Fenêtre COVERAGE-TS-v8 « fan-out multi-auteurs » : 3 nouveaux auteurs
(DeepSeek-V4-Flash, Qwen3.8-2.4T-A95B-NVFP4, GLM-5.2-NVFP4) × sonde 2×2
appels × mêmes tâches validées v7 (zod+date-fns) ⇒ jusqu'à 3 populations
additionnelles mesurées/gatées indépendamment. Enveloppe estimée ~60-80
appels selon sondes. Critère de succès : ≥1 population additionnelle PASS
poison avec négatifs ≥5 ⇒ mix v11 élargi possible.
