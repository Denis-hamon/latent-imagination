# Pré-enregistrement RCT — « consequence-context » (arm fork b0/b1) — v1, 2026-08-10

Scellé AVANT tout appel galere de cette série. Toute modification ultérieure =
amendement loggé ci-dessous AVANT résultats (discipline sealed-envelope du repo).

## Question

Le contexte-conséquence d'un world model (failure-attractors + near-miss outcomes,
G1 mesuré AUC 0.709 goal-free) injecté AU MOMENT de régénérer un patch, améliore-t-il
le taux F2P d'un agent de coding, comparé à une régénération neutre et au draft initial ?

## Design (fork apparié, économe)

| arm | origine | calls galere |
|---|---|---|
| A (contrôle) | draw-3 off-arm existant (9/32 F2P) — réutilisé tel quel | 0 |
| b0 (contrôle « 2ᵉ chance générique ») | fork du draft draw-3 + feedback NEUTRE | 32 (+ retries) |
| b1 (traitement) | fork du MÊME draft + bloc CONSEQUENCE-CONTEXT | 32 (+ retries) |

- Panel : frozen 32 tâches (FR-10, seed 6769) — panel déjà gelé, harness inchangé.
- Le retrieval du bloc b1 **exclut la tâche cible** (`exclude_task`) — anti-fuite
  inter-bras, équivalent production « tâche jamais vue ».
- Chaîne identique aux fenêtres précédentes : extraction full-file>diff, sanitize,
  `git apply` local, 1 apply-retry instrumenté max par arm.
- Modèle : celui des fenêtres frozen32 (PILOT_MODEL fixé au lancement, loggé dans
  call-log ; toute dérive de version côté endpoint frappe b0 et b1 pareil — apparié).

## Budget (compte dans l'enveloppe R10 pré-enregistrée, cap 2000)

- **Cap dur : 100 calls galere** pour la série entière (b0+b1) — attendu ~64–96.
- Arrêt au cap ⇒ publication **partielle** avec % de couverture en header (règle
  disclosure R10 déjà en vigueur).
- 0 call pour l'arm A. 0 h node supplémentaire hors exécution docker existante
  (node_gpu_hours_cap 12 h inchangé).

## Mesures

- **Primaire** : ΔF2P-pass par tâche, McNemar exact sur discordances
  (b1 vs A ; b1 vs b0 ; b0 vs A), publié **quel que soit le signe**.
- **Secondaires** : taux d'application, nb d'apply-retries, tokens (usage loggé).
- Si |Δ| < 5 pts : l'artefact publié = l'instrument + ce négatif ; le design doc
  (`docs/world-model-mcp-design.md` §4) l'annonce déjà.

## Menaces déclarées d'avance

1. Arm A datée (draft draw-3) vs b0/b1 frais : la dérive endpoint est commune aux
   deux forks, l'appariement les immunise ; b0 absorbe l'effet « juste une 2ᵉ chance ».
2. 14/32 tâches frozen présentes dans le pool 113 → exclusion par tâche appliquée ;
   le contexte b1 sur ces tâches reste évaluable (retrieval tient la tâche dehors).
3. n=32 par comparaison : IC larges affichés, pas de sur-claim (doctrine branch-iii).

## Runbook (fenêtre node)

```bash
# 1) sync drafts draw-3 → Mac
scp -r "WMEL-gpu-strong:/home/ubuntu/latent-imagination/data/landing/act2-pilot/results" \
      data/landing/act2-pilot/           # slots *-off (patch.diff+meta.json)

# 2) génération des forks b0/b1 depuis le Mac (cap dur 100 in-script)
uv run python scripts/act2/rct_wm_fork.py            # --dry-run d'abord, 0 call

# 3) pousser rct-v1 → node ; lien gold (réutilise control-gold existant)
scp -r data/landing/act2-pilot/rct-v1 \
      "WMEL-gpu-strong:/home/ubuntu/latent-imagination/data/landing/act2-pilot/"
ssh WMEL-gpu-strong 'cd /home/ubuntu/latent-imagination/data/landing/act2-pilot/rct-v1 \
      && ln -sfn ../control-gold control-gold'

# 4) exécution docker (même harness que draw-3)
ssh WMEL-gpu-strong 'cd /home/ubuntu/latent-imagination \
      && PILOT_ARMS=b0,b1 PILOT_CAMPAIGN_DIR=rct-v1 .venv/bin/python scripts/act2/pilot_node_exec.py'

# 5) rapatrier run-result.json ; analyse appariée
uv run python scripts/act2/rct_analyze.py
```

## Amendements

(aucun à l'ouverture — toute ligne ajoutée ici sera datée et antérieure aux résultats)

### Amendement 1 — 2026-08-10, AVANT tout résultat F2P connu

Fenêtre 1 arrêtée volontairement après **29 calls** (b0/b1 partiels, aucun résultat
d'exécution : le node exec n'avait pas commencé). Cause diagnosticquée sur call de
debug dédié (1 call supplémentaire, total 30 — comptés dans l'enveloppe R10) :

1. **Bug extraction (repo historique)** : `extract_diff` ne capturait que le 1er bloc
   fenced (le modèle en émet ~30 avec son raisonnement) et `sanitize_diff` tronquait
   au 1er saut de ligne (contexte vides désespacés) → diffs sans corps, « no net
   change ». Fenêtres passées épargnées (extraction full-file dominante à l'époque),
   mais la fenêtre 1 du RCT l'a déclenché massivement (taux d'application ~17 %).
   **Fix** : `extract_diff_v2` consolidé multi-blocs + lignes vides = contexte,
   **côté b uniquement** (`rct_wm_fork.py`) — l'arm A (draw-3) garde sa chaîne
   d'origine ; le contraste causal clé (b1 vs b0) partage la même chaîne fixée.
2. **Roaming inter-fichiers** : la régénération éditait un autre fichier que la cible
   (harness mono-fichier) → renforcement HARD CONSTRAINT cible unique dans les deux
   suffixes b0/b1 (symétrique).

Sorties de la fenêtre 1 (29 calls) **écartées** : `rct-v1/discarded-window-1/`
(audit trail conservé). Nouvelle fenêtre complète relancée sous amendement ;
call-log reparti à zéro, cap dur 100 **inchangé** (le cap ne couvre que la série
publiée ; les 30 calls écartés sont du budget R10 global séparé).

### Amendement 2 — 2026-08-10, AVANT tout résultat F2P connu

Fenêtre 2 stoppée après **28 calls** (0/14 slot applicable, toutes arms confondues)
+ call de debug à chaque arrêt. Cause structurelle, diagnostic appuyé sur les raw
replies (désormais persistées par slot — verte) : le suffixe « ONLY unified diff »
fermait le chemin **fichier-complet** (`mode regenerated`) qui portait historiquement
~40 % d'application, et un modèle en régénération aligne ses contextes de hunk sur
**sa version précédente**, pas sur l'original → mismatch systématique.
**Fix** : le prompt accepte explicitement diff OU fichier complet (```python),
rappel « hunk contexts must match CURRENT CONTENT verbatim » — symétrique b0/b1.
Fenêtre 2 écartée : `rct-v1/discarded-window-2/`. Spend R10 2026-08-10 : **59 calls**
(29+debug w1, 28 w2, comptés dans `budget-v1.toml`, hors série publiée).
Cap dur 100 de la série publiée inchangé ; toujours **aucun résultat F2P consulté**.

### Amendement 3 — 2026-08-10, AVANT tout résultat F2P connu

Fenêtre-sonde (2 tâches × 2 arms, 6 calls) : b0 applique 2/2 via full-file,
b1 0/2 — lecture des raw replies : le modèle **écrit ses hunks contre la version
upstream mémorisée du package** (packages swe-smith célèbres dans les données
d'entraînement), pas contre le fichier muté — mismatch de contexte garanti en mode
diff, quelle que soit la consigne. **Fix** : les deux arms passent en **fichier
complet uniquement** (le mode `regenerated` historique du harness) avec avertissement
explicite anti-mémorisation ; le diff final est produit par difflib déterministe
(`make_diff`) → application garantie par construction. Sonde écartée :
`rct-v1/discarded-window-3/`. Spend R10 2026-08-10 : **65 calls**. Cap série
publiée inchangé (100). Résultats F2P : toujours non consultés.

### Amendement 4 — 2026-08-10, AVANT tout résultat F2P connu

Fenêtre 4 (première sous protocole stabilisé amendements 1-3) interrompue à
**79 calls** par un **502 transitoire de l'endpoint galere** (crash process, pas un
choix de protocole). Reprise idempotente : les slots déjà écrits (meta.json présent,
quel que soit l'outcome — patch ou échec honnête) sont **gelés** ; seuls les slots
jamais tentés continuent ; `call_model` côté fork gagne un retry borné sur 502
(3 × backoff 20-60 s). Le cap 100 couvre la série publiée fenêtre-4 incluse ; les
fenêtres écartées (w1/w2/w3 = 65 calls) restent en budget R10 debug séparé.
Spend série en cours : **79** ; reprise estimée ≤ 21 calls → total ≤ 100.
Résultats F2P : toujours non consultés.

## Scellement

- Ce fichier ne contient volontairement AUCUN hash de lui-même (auto-référence
  impossible). L'identité gelée vit dans le ledger : chain = sha256 canonique de
  {sha256(ce fichier), code_commit git, sha256(panel frozen32)}.
- Preuve : `data/release-store/prereg-ledger.jsonl` (type `rct-prereg`) +
  `data/release-store/proofs/<chain16>.ots` (OpenTimestamps).
- Vérification tierce : recalculer la chain_hash depuis les 3 composantes publiques,
  comparer au ledger, vérifier la preuve OTS offline.
