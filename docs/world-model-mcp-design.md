# World Model customized → MCP : design pour un banger (2026-08-10, session de nuit)

Question posée : comment un world model customized (approche SCAMPER), servi en MCP
*à l'image de Context7*, peut améliorer les performances des LLM sur des tâches de coding.

Doctrine de la maison appliquée ici : **rien n'est affirmé sans mesure LOAO du jour**.
Chaque claim de ce doc renvoie à un artefact.

---

## 1. La mesure qui décide la forme du produit (G1, cette nuit)

En production il n'y a **pas de gold patch**. L'énergie E4 (AUC 0.817) en consomme un.
Gate G1 sur le pool (n=113, 69 tâches, LOAO-strict, seuil médiane-train) :

| score | AUC | acc LOAO | lecture |
|---|---|---|---|
| GOLD (contrôle) | 0.817 | 0.735 [0.646,0.807] | reproduction exacte |
| R1 but retrievé 1-NN | 0.556 | 0.540 | **mort** (McNemar p=0.005 vs GOLD) |
| R3 buts top-3 moyens | 0.578 | 0.566 | faible |
| **F1 failure-attractor** | **0.709** | 0.637 [0.545,0.720] | **vivant, zéro notion de but** |
| K5V vote k-NN vanilla | 0.667 | 0.593 | le framing attracteur ajoute +0.042 AUC |
| PERM (contrôle) | 0.479 | 0.478 | protocole sain |

Spearman(énergie GOLD, F1) = **+0.187** → les deux signaux sont presque orthogonaux.
Rang-moyen GOLD+F1 = **AUC 0.838** (+0.021 sur GOLD seul).
Artefact : `data/landing/act2-pilot/g1-goal-free.json`, script `scripts/act2/g1_goal_free_energy.py`.

**Trois faits, pas des opinions :**
1. L'énergie est **goal-bound** : la destination *spécifique* porte l'information,
   un but emprunté ne transfère pas.
2. La **proximité aux échecs passés** est un signal libre de tout but, qui bat le
   retrieval vanilla.
3. Les deux axes **se combinent** → instrumentation à deux axes :
   - *direction-vers-le-but* : disponible là où le but existe (harness d'éval,
     benchmarks, tests de la MR — l'utilisateur fournit `goal_text`)
   - *répulsion-des-échecs* : toujours disponible (le pool grandit à chaque appel
     `report_outcome` — déjà câblé dans le MCP live)

## 2. Triage du corpus sous la focale MCP (12 papiers relus ce soir)

**Tier 1 — porteurs du design :**
| Papier | Mécanique | Transfert Soft-Eng |
|---|---|---|
| LaT-PFN (2405.10093) | in-context learning **dans l'espace latent**, zero-shot, amortisé PFN | le paradigme MCP exact : prédiction latente à tool-time, sans gradient |
| VLA-JEPA (2602.10098) | (état, action, futur-latent), futur = supervision **jamais input** | notre discipline LOAO/gold-séparation a son formalisme canonique |
| LLM-JEPA (2509.14252) | objectif latent > input-space sur LLM (GSM8K, Spider) | la prémisse "coder en latent" validée en langage |
| LeWM (2603.19312) + LeJEPA (2511.08544) | 2 losses (next-emb + reg gaussienne), 15M params, 1 GPU | un code-WM propriétaire est **abordable** ; sélection sans labels |
| Causal-JEPA (2602.11389) | masquage latent contrefactuel par objet | attribution de hunk → warnings **explicables** ("ce hunk-ci porte le risque") |

**Tier 2 — support :** JEPA4Rec (sessions d'édition = séquences, low-resource),
Koopman (2511.09783 — détecteur de régime de session : converge vs boucle),
MC-JEPA (factoring mouvement/contenu = diff/état), Var-JEPA (abstention par variance),
Destrade/Toso (paysage ; orthogonalité E5 mesurée ici), Yu (aux denses ; tie mesuré).

**Tier 3 — écosystème :** stable-worldmodel (2605.21800) — la vidéo a sa plateforme
de benchmarks reproductibles ; **le code-agent n'a rien**. Le gap est documenté par
les autres, pas par nous.

**Le trou dans la littérature, noir sur blanc :** tout JEPA×LLM est *training-time*
(LLM-JEPA : pretrain/finetune). Personne ne fait tourner la structure JEPA à
*tool-time*, comme service d'in-context latent prediction. C'est exactement ce
qu'un MCP est.

## 3. SCAMPER sur les actifs mesurés (et rien d'autre)

| lettre | option | actif mesuré qui la porte |
|---|---|---|
| **S**ubstituer | verdict → **contexte** ; but gold → but fourni par le caller (harness) | E1 a tué le steering (1/32=1/32) ; G1-F1 vit sans but (0.709) |
| **C**ombiner | énergie-but × attracteur-échecs × near-miss outcomes | GOLD+F1 → 0.838 mesuré ; near-miss déjà live (dédupé) |
| **A**dapter | le pattern Context7 (injecter docs fraîches) → injecter **conséquences** ("ce que le monde renvoie") | Context7 prouve le canal ; rien à inventer côté transport |
| **M**odifier | par-patch → par-**session** : détecteur de régime (boucle/converge) | Koopan : JEPA apprend les indicateurs de régime ; nos logs MCP ont les séries |
| **P**ut to other use | le pool comme **benchmark-and-trace store** pour tiers (éval infra) | AUC populationnelle 0.817+IC ; 10 verdicts publiés honnêtement |
| **E**liminer | le seuil dur ; le gold requis ; l'encodeur fine-tuné | 3 égalités E1/E2/E6 : on peut jeter sans rien perdre (E2 fine-tune détruit : AUC 0.513) |
| **R**everser | au lieu de "est-ce bon ?" → "où ça casse ?" : **failure-attractors + hunk fautif** | F1 0.709 ; Causal-JEPA donne la mécanique d'attribution |

## 4. Stress-test — trois angles, un banger

| angle | qui l'a déjà | ce qui le tue | verdict |
|---|---|---|---|
| A. **Tool-time WM context (2 axes) via MCP** | personne (LLM-JEPA = training-time) | ΔF2P trop faible au RCT → mitigé : infra + négatifs tiennent seuls | **LE BANGER** |
| B. Eval-infrastructure ERBVE population | harness papers nombreux | moins de nouveauté | fallback, section du papier |
| C. Code-WM propriétaire entraîné (recette LeWM) | EB-JEPA/LeWM en vidéo | n=113 trop petit pour from-scratch ; E2-négatif | future work |

**Thèse du banger.**
*Context7 dit au modèle ce que le monde **est** (docs fraîches). Notre MCP dit au modèle
ce que le monde **fait en retour** (conséquences exécutables). Première world-model
servie à tool-time : deux axes mesurés (direction-vers-but 0.817, répulsion-des-échecs
0.709, combinés 0.838), négatifs publiés (steering best-of-K = hasard ; buts retrievés
morts), et un RCT pré-enregistré qui mesure si le contexte-conséquence améliore le
ΔF2P d'un agent — la question business réelle, tranchée par les tests de la tâche,
pas par un juge.*

Titre de travail : **"Tool-Time World Models: Executable-Consequence Context for
Coding Agents"**. Section d'honneur : tout ce qui ne marche pas (E1-boltzmann, E2,
R1) avec les artefacts — la crédibilité *est* le différenciateur.

## 5. RCT pré-enregistré (la preuve business manquante)

- **Panel** : frozen 32 tâches (déjà gelées FR-10, seed 6769), harness identique.
- **Arm A** : agent vanilla (re-run du protocole existant — 32 calls galere).
- **Arm B** : même agent, même prompt, + bloc contexte injecté avant génération du
  diff : (i) score attracteur du brouillon courant après 1er jet facultatif,
  (ii) 3 near-miss dédupés avec outcomes, (iii) régime de session. 32 calls +
  retries instrumentés identiques.
- **Mesure primaire** : ΔF2P-pass B−A, apparié par tâche (McNemar sur flips).
- **Secondaires** : taux d'application du diff, nb de retries, tokens.
- **Budget** : ~70-100 calls sur les 247 restants — dans l'enveloppe jour 2000.
- **Règle d'arrêt et publication** : effet + IC95 publiés **quel que soit le signe** ;
  si |Δ| < 5 pts, le papier publie l'instrument + les négatifs (affirmé d'avance).
- Budget R10 à pré-enregistrer par l'humain avant tout spend (comme d'habitude).

**Exécution (2026-08-10, machine livrée, 0 call)** : fork apparié du draft draw-3 —
b0 (feedback neutre, contrôle « 2ᵉ chance ») vs b1 (bloc consequence-context) —
32 tâches, **cap dur 100 calls**. Pré-enregistrement scellé + runbook :
`governance/act2/rct-prereg-v1.md`. Scripts : `scripts/act2/wm_context.py`
(constructeur du bloc, anti-fuite `exclude_task`), `rct_wm_fork.py` (runner,
`--dry-run` vérifié : 64 slots, 0 call), `rct_analyze.py` (McNemar apparié).
Node : `pilot_node_exec.py` accepte désormais `PILOT_ARMS=b0,b1`. Côté produit :
4ᵉ tool MCP `risk_scan` (l'axe goal-free 0.709) live-testé dans
`scripts/mcp/energy_gate_server.py`. Reste à la main de l'owner : signature du
prereg + 5 commandes du runbook (dont ~64-96 calls galere).

## 6. Risques honnêtes

1. n=113, IC larges visibles ; F1 acc [0.545,0.720] croise la majorité → le score
   est un **rang**, pas un verdict.
2. Le RCT peut être nul → plan de publication déjà écrit pour ce cas.
3. Généralisation : bugs injectés, un LLM auteur, mono-hunk 95 % → extension
   organique = corpus v1, pas promesse.
4. Le goal-axis suppose un but fourni ; hors harness, l'utilisateur peut fournir
   l'énoncé de tests — validité de CE proxy non mesurée (next : G2 sur le panel).

## 7. Suivi

- Artefacts nuit : `g1-goal-free.json`, `scripts/act2/g1_goal_free_energy.py`.
- Rapport de campagne : addendum dans `governance/act2/pilot-phase-report.md`.
- MCP live : `scripts/mcp/energy_gate_server.py` — extension 2-axes = le chantier code qui suit le RCT.
