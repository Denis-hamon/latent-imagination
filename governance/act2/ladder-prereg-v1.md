# Pré-enregistrement ladder-v1 — baselines absolues 2 modèles sur panel gelé — 2026-08-10

Scellé AVANT tout appel de cette série (même discipline que rct-prereg-v1 :
chaîne hash → ancre OTS → ledger).

## Question

Sur le MÊME panel gelé 32 tâches (FR-10, seed 6769) et le MÊME harness validé
(extraction full-file régénérée deterministic via difflib), quel taux F2P absolu
obtiennent deux modèles plus récents du roster galere — en mesure directement
comparable aux 0.125 de l'arm A RCT (Qwen3.6-35B, fenêtre 08-08) ?

Motivation déclarée : le RCT a montré une base faible et un effet nul du contexte
WM à ce régime ; avant toute claim « performances adéquates », il faut le niveau
absolu de modèles plus forts sur ce panel.

## Design

| arm | modèle galere | calls |
|---|---|---|
| m-deepseek | `DeepSeek-V4-Flash-max` | 32 |
| m-glm | `GLM-5.2-NVFP4` | 32 |

- Prompt : `base_prompt` full-file de `rct_wm_fork.py` (identique aux arms b0/b1
  du RCT — comparabilité interne), SANS bloc draft/feedback : un seul appel par
  (modèle × tâche), **aucun** apply-retry (discipline de cap).
- ITT : slot sans candidat = F2P échec.
- **Cap dur : 64 calls au total** (33ᵉ appel d'un modèle impossible). Arrêt au cap
  ⇒ publication partielle avec % de couverture (règle disclosure R10).
- Enveloppe : R10 cap 2000 — 65 debug + 100 série RCT déjà consommés aujourd'hui
  sur les ~247 libres du 08-08 ⇒ ~82 libres ; 64 ≤ 82, **aucune extension
  d'enveloppe demandée**.

## Mesures

F2P/pass par modèle (Wilson95), comparaison descriptive à l'arm A historique
(0.125, même panel, sous-groupe modèle différent — la comparaison inter-modèles
n'est PAS appariée temporellement : déclarée descriptive, pas causale).
Publication quel que soit le signe, y compris « les nouveaux modèles ne font pas
mieux ».

## Menaces déclarées d'avance

1. Roster instable (retrait de Qwen3.6 en plein RCT) — si un modèle disparaît
   mid-ladder, publication partielle avec le modèle de substitution NON autorisé :
   on publie la couverture du modèle d'origine, point.
2. Mesures historiques 08-08 non contemporaines : la dérive endpoint est réelle →
   les deltas vs arm A sont présentés comme indicatifs.

## Scellement

Aucun hash in-file. Chaîne : {sha256(ce fichier), code_commit, sha256(panel)}
→ ledger `prereg-ledger.jsonl`, preuve `proofs/<prefix>.ots`.

## Amendement 1 — 2026-08-10, AVANT tout résultat F2P consulté

**DIVULGATION DE PROCESS** : les 17 calls ci-dessous ont été dépensés AVANT le
scellement OTS de ce prereg (inversion freeze→spend de l'opérateur ; la série
publiée partira, elle, scellée).

Fenêtre 1 stoppée à **17 calls** (16 « no-diff », 1 regenerated). Cause : les
modèles à raisonnement long (DeepSeek-V4-Flash-max) émettent des dizaines de
blocs ```python de réflexion ; l'extraction canonique prenait le PREMIER (un
snippet) → rejet systématique au garde-fou 0.5. **Fix** : le runner ladder retient
le bloc ```python **le plus long**, puis chaîne canonique identique (garde 0.5,
make_diff difflib). Symétrique entre les deux modèles. Fenêtre 1 écartée :
`ladder-v1/discarded-window-1/` — les 17 calls partent au debug R10 du jour
(total 2026-08-10 : 82 calls debug + 100 série RCT). Reste ~65 sous enveloppe 2000 :
**le cap 64 tient sans extension**. Résultats F2P : non consultés.
