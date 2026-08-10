# Synthèse littérature Code-WM (exécution/simulation) → Latent-Imagination (2026-08-10)

Vague 2 de la revue, après `literature-synthesis-wmm.md` (JEPA générique → mesuré
tiède chez nous : E1/E2/E6 égalités, E3 irrecevable). **Question filtrante inchangée** :
améliorer l'instrument (état, diff) → P(F2P passent), pool v6 n=145, LOAO strict,
0 call galere préféré, 2× L40S de compute local quand le node est up.

Liste complète reçue de l'owner (6 catégories), **triée garder/éjecter** au regard de
cette question — pas de la valeur intrinsèque des papiers.

---

## 1. GARDER — les 4 qui changent quelque chose chez nous

| Papier | Thèse | Résultat clé | Ce qu'il change pour nous |
|---|---|---|---|
| **CWM** (Meta FAIR, 2510.02387) | LLM 32B mid-entraîné obs-action : traces Python (120 M fns) + ForagerAgent docker (3 M traj., mutate-fix = **notre paradigme swe-smith**) | 65.8 % SWE-bench Verified ; ablation : traces → CruxEval seul, **ForagerAgent → +3.7 pts SBV** ; poids ouverts gated-manual | candidat encodeur « dynamique pure » → **S8**. La donnée qui porte est obs-action multi-pas, pas la trace JSON |
| **Rahmani — Debugging CWM** (2602.07672) | échecs CWM : budget tokens, état **string** (71 % fautes CruxEval-O), **hallucination d'actions** | teacher forcing (actions *données*) → propagation juste >128 steps | on **donne** l'action (le diff) : pile dans leur régime fort ; E1 (choisir l'action) = leur régime faible — expliqué. → stratifier par famille de mutation (strings vs opérateurs) ; forme score > forme trace |
| **Self-Execution Simulation** (2604.03253) | SFT traces NL (NLEX ~80 M) + RLVR output-prediction → best@k simulé, self-fix | best@k-simulate **+2-8 pts** ; CWM-OutPred filtre les solutions **d'un autre modèle** ; **ablation : scaffold sans post-training = −10 à −20 pts** | le plus actionnable → **S9 réécrite** : pas de scoreur gratuit par prompting (mort-né d'après leur Table 4) ; post-training de prédiction per-test sur notre pool (cible `per-test.json` existante) avec backbone 7B/32B |
| **Current Agents Fail to Leverage WM for Foresight** (2601.03905, Qian et al.) | agents VLM : <1 % invoquent la simulation, ~15 % la misusent, jusqu'à −5 % quand elle est imposée ; bottleneck = *quand* simuler / interpréter / intégrer | négatif externe, modalité **vision/VQA (pas code)** — précision d'honnêteté | **corrobore notre RCT 08-10c** (contexte-conséquence injecté → n.s., estimation négative) : deux modalités, même mur — l'injection de foresight ne sert pas l'agent non entraîné à l'exploiter. À citer dans le papier |

## 2. ÉJECTER — avec verdict (scope, pas mérite)

| papier | pourquoi hors de notre question |
|---|---|
| TRACED (2306.07487) | absorbé par W1/W5 (précurseur CodeT5-scale) ; candidat encodeur « option C » seulement |
| NExT (2404.14662) | absorbé dans NLEX (W5) — la forme NL gagne sur JSON, noté, rien à mesurer de plus |
| **GIF-MCTS / CWMB** (2405.15383) | le LLM *écrit le code* d'un WM pour un agent RL classique — chez nous le WM = les poids. Orthogonal à (état, diff) → F2P |
| **WorldEvolver** (2606.30639) | mémoire épisodique + filtrage sélectif des prédictions : converge *conceptuellement* avec S1 (abstention) mais cadre planning générique, aucun artefact testable sur notre pool |
| Agentic World Modeling (2604.22748) | survey — redondant avec les deux vagues déjà couvertes |
| Computer-using WM (2602.17365) | modalité GUI — hors scope code |
| World of Workflows (2601.22130) | workflows d'entreprise — hors scope |
| Text2World (2502.13092) | génération de WM *symboliques* — même classe que GIF-MCTS, autre objet |
| Agentic Environment Engineering survey (2606.12191) | contexte bibliographique seulement |
| Awesome-World-Model (dépôt) | déjà couvert par la vague 1 (`literature-synthesis-wmm.md`) |

Le gap reste confirmé : **aucun de ces benchmarks ne mesure (état, diff) → tests** —
notre position « le code-agent n'a pas son stable-worldmodel » tient après les 2 vagues.

---

## 3. Convergence avec nos mesures (le tableau qui compte)

| chez nous (mesuré) | chez eux (mesuré) | lecture commune |
|---|---|---|
| E1 : best-of-4 par énergie latente = hasard (1/32=1/32) | W5 Table 4 : scaffold self-RLEF sur modèles non entraînés **dégrade** (−10.6/−20.1) | **aucun scoreur gratuit n'existe** : ni distance latente ni simulation promptée — la sélection s'entraîne |
| énergie (état,diff)→gold : AUC 0.82-0.86 (action donnée) | W2 : sous actions données (TF), CWM propage l'état juste >128 steps | le régime « action donnée » est la place forte des deux côtés |
| E6 : auxiliaire per-test neutre *à n=113 sur uxc gelé + tête MLP* | W5 : output-prediction per-test ENTRAÎNÉE sur 32B = 85 pass@1 | E6 n'invalide pas la cible per-test — il invalide la cible per-test *sans capacité de simulation dans le backbone* |
| recovered (diffs réparés) = poison, AUC 0.543 | W2 : la surface textuelle (tokenisation) pilote les échecs | la fidélité textuelle est un invariant partagé |
| RCT contexte-conséquence : n.s., estimation négative (08-10c) | 2601.03905 : foresight <1 % invoquée, jusqu'à −5 % si imposée | l'injection de foresight ne sert pas l'agent (deux modalités, même mur) |

## 4. Roadmap résultante (ordre révisé)

1. **S8** — CWM-pretrain encodeur gelé vs tableau S4. Bloqué : node down + gated-manual Meta (demande owner en cours). Fallback prêt : Qwen2.5-Coder-7B-Instruct (déjà téléchargé sur le node).
2. **S9'** — post-training prédiction **per-test** : LoRA sur Qwen2.5-Coder-7B (ou CWM si licence), cible = verdicts per-test du pool, budget 2× L40S, **critère déclaré d'avance** : LOAO acc > 0.779 et cov@≥0.95 > 25 % (v6 GOLD). C'est E6 avec capacité de simulation dans le backbone.
3. **Stratification par famille de mutation** (strings/opérateurs — W2) ajoutée à toute éval future.
4. **Papier** : section négatifs enrichie de la corroboration 2601.03905 (avec la nuance modalité).

## 5. Blocages opérationnels au 2026-08-10 soir

- Node WMEL-gpu-strong **down depuis ~20:14** (post-TERM du vLLM OpenResearcher — corrélation notée, causation non établie ; KVM côté owner).
- `facebook/cwm*` gated **manual** chez Meta — demande d'accès à faire (compte HF owner ; token read déjà déposé sur le node).
- vLLM OpenResearcher à relancer au retour du node : `bash /home/ubuntu/restart-openresearcher-vllm.sh` (commande d'origine préservée).
