# Menu d'expérimentations Ghost — après v45

**Statut** : plan de travail actif, pas un prereg de fenêtre unique — chaque
expérience listée ci-dessous (E1…E9) devient sa propre fenêtre `window-vNN-*`
avec grille de décision scellée quand elle est lancée, selon le gabarit déjà
en usage dans ce dossier (voir `window-v45-llm-judge-proposal.md`).

**Note pour l'exécutant (Qwen)** : ce document est le carnet de route. Avant
de lancer une expérience de la Phase 1+, vérifier dans le journal ci-dessous
qu'elle n'est pas déjà close, gelée ou gatée par une autre. Ne jamais citer un
chiffre de v45 sans avoir relancé `scripts/act2/w45_judge_metrics.py` (Action
zéro, plus bas) si le retry Qwen/GLM n'était pas terminé au moment de la
lecture.

## Contexte

Doute de départ : Ghost peut-il atteindre des performances qui complètent réellement
les LLM sur son domaine (prédiction d'issue de patch), ou plafonne-t-il sans jamais
justifier l'effort ? Le ledger (`_bmad-output/implementation-artifacts/deferred-work.md`,
DW-31→63) montre deux axes déjà clos (classifieur goal-free cd-only : plafond AUC
0,69–0,75, DW-46 ; goal-ranking intra-ticket : réfuté, DW-51) et un seul axe vivant et
servi : le modèle de transition séquentielle (`predicted_evolution`, v41, v0.8.2 —
AUC 0,9931 / Jaccard 0,9333 LOO-trajectoire).

Une fenêtre `v45` (préregistrée par l'owner le 21/08, `governance/act2/window-v45-llm-judge-proposal.md`)
répond déjà en partie au doute : trois juges LLM zero-shot (DeepSeek-V4-Pro,
Qwen3.8-2.4T, GLM-5.2) confrontés à la même tâche que le modèle de transition.

**État de v45 — FINAL (retry terminé, recalculé le 2026-08-21 ~22:50)** :
process `w45_judge_run.py` éteints, `call-counter-w45.jsonl` stable (22:57),
trois juges complets 180/180. Verdict **G2 confirmé** sur données finales
(`arm-v45-llm-judge-verdict-2026-08-21.json` recalculé) :

| Juge | AUC paires | Jaccard (143 transitions) | parse_ok |
|---|---|---|---|
| GLM-5.2 | 0,833 | **0,462** (meilleur juge) | 105/180 |
| Qwen3.8-2.4T | **0,861** | 0,379 | 123/180 |
| DeepSeek-V4-Pro | 0,804 | 0,194 | 172/180 |
| Persistance | 0,784 | 0,771 | — |
| Modèle v41 | 0,9931 | 0,9333 | — |

Le meilleur juge Jaccard est GLM (0,462), pas Qwen comme estimé sur données
partielles (0,42) ; ça ne change rien au verdict : 0,462 vs 0,9333, l'écart
reste brutal. parse_ok faible = problème de parsing JSON (surtout GLM/Qwen),
les manquants sont imputés STILL_RED conf 50 (conservateur).

**Action zéro : FAITE le 2026-08-21 ~22:50.** Les chiffres ci-dessus sont
ceux de `w45_judge_metrics.py` relancé sur les fichiers complets.

**Leçon méthodologique de v45 à appliquer partout ci-dessous** : l'AUC flatte les
juges (0,855 proche-ish), le Jaccard (la métrique produit réelle) révèle l'écart
brutal. Toute expérience de décision doit trancher sur Jaccard/J, jamais sur l'AUC seul.

## E4 exécuté (2026-08-21) — résultat FINAL (données complètes 180/180)

Recalculé sur les fichiers complets avec `scripts/act2/w45_ece.py` (persisté),
protocole E4 figé : tests `red_from` avec verdict parsé uniquement, ECE 10 bins
égaux sur confiance propre ∈ [0,5 ; 1]. Artefact :
`arm-artifacts/arm-v45-e4-ece-final-2026-08-21.json`.

| Juge | n verdicts | Accuracy (verdicts donnés) | ECE (10 bins) |
|---|---|---|---|
| GLM-5.2 | 335 | 0,570 | **0,310** |
| Qwen3.8-2.4T | 469 | 0,448 | **0,414** |
| DeepSeek-V4-Pro | 646 | 0,401 | **0,491** |
| **Ghost (référence, post-PAV)** | — | — | **0,0205** |

Les trois juges sont massivement **surconfiants** : l'essentiel de leurs
verdicts tombe aux confiances 83-95 %, où leur exactitude réelle va de 0,29
(Qwen, bin 85-90 %) à 0,65 (GLM, bin 80-85 %) — jamais à hauteur de la
confiance affichée. Ghost est 15 à 24× mieux calibré. (Chiffres du 21/08 au matin
— GLM 0,304 / Qwen 0,446 / DeepSeek 0,520 sur données partielles — confirmés
en direction, affinés sur données complètes.) **E4 est clos.**

## E6 exécuté (2026-08-22) — résultat FINAL : A3 EFFONDRÉ

Fenêtre v46 scellée (commit 21682ac). Verdict :
`arm-artifacts/arm-v46-e6-adversarial-verdict-2026-08-22.json`.

**P0 (contrôle positif) : OK mais avec deux findings.** Reconstruction LOO du
modèle v41 = AUC 0,9949 / Jaccard 0,9333 (réf 0,9931/0,9333, dans les tolérances
scellées ±0,005/±0,015). Findings tracés :
1. Le 0,9931 servi est un **LOO par TRANSITION** (180 plis) ; le LOO par
   trajectoire (sans fuite de sœurs) plafonne à AUC 0,9891 / J 0,89-0,95. Le
   chiffre de référence contient donc une fuite de structure intra-trajectoire.
2. Le fichier `v39-transitions.jsonl` a été régénéré (mtime 21/08 00:39) après
   le verdict v41 (20/08 23:27) : la baseline persistance AUC 0,8197 ne s'y
   reproduit plus (0,9083), preuve de dérive de la contingence persist×label.

**P1/P2 (sonde adversariale) : A3.** Sur 250 cas gelés (paires red_from\red_to
où le pli LOO-trajectoire prédisait « réparé ») :
- `flip_R` = **0/250** : inverser l'effet du diff (lignes +/- échangées) ne fait
  JAMAIS repasser la prédiction à « encore rouge ». Idem pour la variante neutre.
- Mécanisme établi en deux étages : l'encodeur jina est quasi aveugle à
  l'inversion de signes (cos(orig, revert) = 0,980 moy sur n=45), ET la tête
  logistique ne dépend pas de Ed pour ces cas (contrôle Ed=0 invariant, Δz brut
  médian −0,15 dans le mauvais sens).
- Conclusion : le signal LOO est porté par persist/Et/frac/turn + contenu de
  surface du diff, **jamais par la direction de son effet**. Le 0,9931 ne peut
  pas s'interpréter comme une compréhension de l'effet des patchs.

**Conséquence scellée — DÉCIDÉE ET EXÉCUTÉE (2026-08-22)** : owner a choisi
**disclosure, pas déotion** (commit 8573aa3 : code + ledger + garde-fou vert).
Déployé sur le nœud servi le 22/08 ~10:41 (fichier synchronisé, service
redémarré, disclosure A3 vérifié EN LIVE dans la réponse `predicted_evolution`).
La colonne reste servie ; chaque réponse porte désormais : signal de surface
(persist/turn/frac + embedding brut), pas une lecture de l'effet du patch.

**Leçon méthodologique (à répercuter)** : la grille v45 prédisait « décider sur
Jaccard, jamais AUC seul » ; E6 montre qu'il faut aller plus loin — ni l'AUC ni
le Jaccard LOO ne détectent l'absence de lecture causale. Seule une sonde
adversariale à effet inversé la révèle. Tout futur bras « compréhension du diff »
doit inclure une sonde revert dès le prereg.

**Leçon transverse — baselines dégénérées dans les grilles Jaccard (2e occurrence, à généraliser)** :
DW-58 (per-test, régime ≥50 % triviales) et v48/E5 (`persist` constant par
construction single-shot+ablation) sont le même piège vu deux fois : un
Jaccard-vs-baseline scellé AVANT d'avoir vérifié que la baseline a une vraie
variance sur la population qui sera réellement mesurée. **Règle à appliquer
à toute future grille Jaccard-vs-baseline** : vérifier la variance de la
baseline sur un échantillon de la population gelée AVANT de sceller le
seuil, pas après avoir vu le résultat. Un T2 échoué contre une baseline
dégénérée ne dit rien sur le modèle — il dit que l'instrument est cassé.

## E8 et E9 — gap découvert en exécutant, pas en spéculant

- **E8 — localisé et vérifié (ni Kimsufi ni le serveur MCP distant — LOCAL) :**
  `product_session.py:168` écrit `data/landing/act2-pilot/mswb/product-session-{ticket}.json`
  à chaque session réelle (`entry["risk_scan"] = rs.get("decision")` par tour).
  Kimsufi (141.95.99.214) ne contient que les dépôts minés (aucun log Ghost) ;
  `ghost-mcp` (51.210.228.117) n'a qu'un log HTTP transport stale du 15/08,
  sans détail métier — la décision `abstain`/verdict n'est jamais persistée
  côté serveur (vérifié dans `ghost_server.py`, elle est seulement retournée
  à l'appelant).
  **Contenu réel (3 sessions/5 tours à ce jour, vuejs__core-11026 + 11761)** :
  `risk_scan` a **abstenu 100 % des tours (5/5)** — cohérent avec son plafond
  connu (DW-46) sur des tickets réellement neufs. Conséquence pour E8 : caler
  le cascade sur l'abstention de `risk_scan` ne filtrerait RIEN sur ces
  données (0 appel évité) — le vrai signal de triage disponible est `pft`
  (per-test) et `pev` (transition), qui eux restent confiants et spécifiques
  (ex. `declare global` à 0,845-0,885 sur les 3 tours — le test dur déjà
  identifié en DW-62/63). **E8 doit être reformulé pour gater sur pft/pev, pas
  sur risk_scan.** n=3 sessions est trop petit pour conclure — Temps reste 1
  (les fichiers existent, le script d'analyse est trivial), mais le résultat
  actuel n'est qu'un aperçu ; attendre que le sweep v44 (20/j) accumule plus
  de sessions avant de trancher.
- **E9** : `judge-inputs.json`/`v39-transitions.jsonl` contiennent la vérité
  terrain (`truth_red_to`) et les verdicts des juges, mais **pas** la
  prédiction propre de Ghost par transition — elle n'est jamais persistée,
  seulement calculée en mémoire lors des runs LOO. Trouver « où le juge a
  raison et Ghost a tort » exige d'invoquer `predict_transition()` en direct
  (chargement du modèle, potentiellement sur le nœud GPU distant) — pas un
  simple croisement de fichiers comme scopé initialement. **AUTORISÉ le
  2026-08-22** (décision owner scellée dans `window-v46-e6-adversarial-transition-proposal.md`) :
  à la suite du contrôle positif P0 de v46 (harnais LOO reconstruit et
  validé localement), réutiliser la même instance pour invoquer
  `predict_transition()` sur les 180 transitions et persister la prédiction
  Ghost par transition — coût marginal nul, pas de nouvel appel LLM, pas de
  dépendance au nœud GPU. Mesure séparée de v46, à ne pas pooler dans son
  verdict A1/A2/A3.

## Menu d'expérimentations

Notes : Impact/Innovation sur 5 (5 = le plus). Temps sur 5 (1 = quelques heures,
2 = 2-3 j, 3 = ~1 semaine, 4 = 2-4 semaines, 5 = incertain / dépend d'une inconnue
non résolue, potentiellement >4 semaines). Chaque estimation de temps ci-dessous a
été vérifiée contre les chemins de fichiers réels (pas une estimation en l'air) —
sauf mention contraire explicite.

| # | Expérimentation | Impact | Innovation | Temps | Pourquoi ce score |
|---|---|---|---|---|---|
| E4 | **Calibration LLM auto-déclarée vs ECE Ghost.** Le champ `conf 0-100` existe déjà, peuplé, dans `judge-outputs-*.jsonl` de w45. Comparer son ECE à celui de Ghost déjà mesuré (0,0205 post-PAV, `arm-pert-test-isotonic-prereg.md`). Zéro nouvel appel. | 4 | 3 | **1** | **CLOS** — voir résultat ci-dessus |
| E9 | **Carte d'erreur localisée depuis les divergences w45.** Croiser `judge-outputs-*.jsonl` × `v39-transitions.jsonl` × issues groundées existantes : chercher un sous-ensemble structuré où c'est le JUGE qui a raison et Ghost qui se trompe. | 4 | 4 | **1** (≤2 j) | **CLOS (2026-08-22)** — 12 cas structurés (seuil ≥5 atteint), 100 % fausses alarmes Ghost sur tests réparés, accord ≥2 juges sur les 12 ; voir `w46/e9-errormap.json`. Donne sa cible à E1 |
| E8 | **Signal cascade/triage rétrospectif.** Sur les logs déjà groundés : combien d'appels LLM auraient été évités si Ghost filtrait en amont ? | 3 *(révisé de 4)* | 3 | **1** (≤2 j) | **À REFORMULER** — gater sur pft/pev, pas sur risk_scan (voir ci-dessus). Attendre plus de sessions (sweep v44) |
| E6 | **Sondage adversarial du modèle de transition.** Construire des quasi-diffs (même syntaxe, effet sémantique inversé) et vérifier si `predict_transition()` (`latent-imagination/scripts/mcp/ghost_server.py:309-351`, pool `_load_transition():290-306`) s'effondre. Jamais fait — `near_mis_patches` n'a servi qu'à la sélection informative, jamais au stress-test. | **5** | 4 | **2** (2-3 j) | **CLOS — A3 EFFONDRÉ** (fenêtre v46, verdict 2026-08-22) : flip_R = 0/250, le modèle ne distingue pas un diff de son inverse ; voir section résultat ci-dessous |
| E2 | **Étendre le gabarit w45 (prereg + grille G1/G2/G3) à l'axe per-test** (`compare_patches`, J servi 0,80). Décision sur Jaccard/J, jamais sur AUC seul. | 3 *(révisé de 4)* | 2 | **2** (2-3 j) | DW-58 a déjà établi que le per-test servi est bien calibré (Brier 0,1035) — confirmera probablement un G2-like ; utile pour la complétude, pas décisif |
| E1 | **Durcir la classe rare** (DW-62, 30 positifs). Cible identifiée par E9 (clos 22/08) : les 12 cas « juge a raison, Ghost a tort » sont 100 % des FAUSSES ALERTES Ghost (persist=1, le diff répare, Ghost prédit rouge à tort). La classe rare à durcir n'est PAS « ajouter des positifs encore-rouge » mais « apprendre à Ghost qu'un diff peut RÉPARER un test rouge » (signal anti-persistence). **v47 (sign-split embedding) EXÉCUTÉE (2026-08-22) : V3 PERDU** — R12 = 1/12 fausses alertes réparées (cible ≥4), flip_R sonde revert = 0,042 (cible ≥0,35), AUC/J25 en légère régression vs baseline. Mécanisme : cos(E_add,E_del) = 0,58, la composante antisymétrique de l'embedding jina est trop faible pour porter la direction. **La voie embedding (plain A3 + sign-split v47) est fermée.** Pivot scellé : features STRUCTURELLES pures (comptes add/del par hunk, pas d'embedding) ou s'appuyer sur E3 (ablation, déjà validé en V2 PARTIEL). | 3 *(révisé de 4)* | 2 | **3** (~1 semaine) | Deux voies fermées en une nuit (A3 puis v47) resserrent utilement l'espace : la direction d'effet n'est pas dans l'embedding, elle doit venir d'une représentation structurelle ou de l'exécution (E3) — pas du volume au hasard, piège DW-37 |
| E5 | **Transfert cross-langue du modèle de TRANSITION** (pas le classifieur cd-only, déjà raté en TS, DW-49) sur repos Python/Go déjà instrumentés par SWE-smith. **Vérifié directement** : `swe-smith-trajectories/smith-matched-full/matched-items.json` (18 547 lignes) est du **single-shot** (`instance_id, model, patch, resolved, source` — un seul patch, un seul booléen, aucune séquence red_t→diff→red_t+1) ; `swe-smith-tasks/` = énoncés seuls. **Aucune trajectoire séquentielle n'existe dans ce pool.** **FINDING 2026-08-22 (smoke Kimsufi)** : RED reproductible en 15 s (boltons, 2/2 F2P échouent, pytest 0,07 s, image x86_64 native sur Kimsufi), MAIS les labels `resolved` sont inutilisables tels quels — **72,7 % des 5 460 patches résolus ciblent le mauvais repo** (matching amont croisé) ; seuls ~1 407 passent l'heuristique de cohérence, et la vérité-terrain ne peut venir que de l'exécution (gates RED/GREEN empiriques). | **5** | 4 | **3** (~1 semaine) | **v48 EXÉCUTÉE (2026-08-22) : S2 PARTIEL** — P1 Kimsufi 1 143 transitions dédupliquées (413 full-fix + 730 ablations dont 279 à red_to non vide, 6 repos), gate ≥150 largement passé ; P2 : Bras B refit Python AUC 0,924 / Jaccard 0,688, Bras A zero-shot v41 AUC 0,499 / Jaccard 0,004 (hasard — périmètre JS/TS confirmé). DIVULGATIONS : baseline [persist] dégénérée (persist constant par construction ⇒ AUC baseline 0,5), AUC agrégé dominé par pandas (73 % des paires, 13 positifs ; hors pandas 0,51-0,79). Pas de serving Python. **DÉCIDÉ owner (22/08) : ni clôture ni P3 — amendement n°3 en cours** : le T2 (Jaccard) est cassé par construction (single-shot+ablation force persist=1 constant, Jaccard baseline 0,777 = artefact du déséquilibre de classe, même piège que DW-58). Protocole scellé : définir la baseline non-dégénérée (exclusion single-shot) et sceller son seuil AVANT tout recalcul — interdiction explicite de réutiliser le 0,884 « ablations seules » déjà observé comme clôture (grid-shopping post-hoc, piège DW-37). Voir `arm-v48-e5-transfer-verdict-2026-08-22.json` + amendement n°3 dans `window-v48-e5-swesmith-transfer-proposal.md` |
| E3 | **Attribution/ablation contre-factuelle au hunk.** Ré-exécuter les tests en retirant un hunk à la fois sur le stock RED-GREEN déjà vérifié, zéro appel LLM, nouveau signal de blâme localisé (critique injectable dans une boucle d'agent). | **5** | **5** | **3** *(révisé de 5 — gates levées 22/08)* | **v49 EXÉCUTÉE (2026-08-22) : V2 PARTIEL** — C1 infra 1,0 (33/33 tickets, 132 hunks, mécanisme VALIDÉ), C2 cohérence 0,76 (4 épistasies pures + 3 dayjs flaky), C3 volume 76 paires causales (<100). 82 % des tests baseline blâmés. Trouvailles : épistasie réelle (15 % des tickets), flaky jest×4TZ identifié. Actif dans `w49/ablation-blame.jsonl` ; le mécanisme validé est porté à la campagne Python v48 (769 instances) pour la densité |

**Note d'infra transverse (pas une expérimentation)** : factoriser la fonction
d'appel LLM, dupliquée dans exactement 3 endroits confirmés (`w45_judge_run.py:42`,
`s13_llm_judge.py:96`, `real_ticket_harvest.py:112` — la constante `GALERE` elle,
est déjà centralisée et importée par `real_ticket_harvest.py`). Demi-journée, pas
un chantier ; à faire avant E2 si E2 ajoute un 4e point d'appel dupliqué.

## Séquence et dépendances

```
Phase 0 (données déjà sur disque)
  E4 ─┐  CLOS
  E9 ─┼─→ CLOS (2026-08-22) : 12 cas structurés « juge a raison, Ghost a tort »,
          100 % fausses alertes Ghost sur tests réparés — donne sa cible à E1
  E8 ─┘  À REFORMULER (gater sur pft/pev)

Phase 1
  E6 → CLOS : fenêtre v46 verdict A3 EFFONDRÉ (2026-08-22). Le modèle servi ne
       lit pas la direction d'effet des diffs. Revue de serving à décider (owner).
  E2 (complétude, pas de dépendance dure avec E6)

Phase 2 (conditionnée aux résultats)
  E1 ← dé-gatée : E9 a identifié la cible (12 cas fausses alertes Ghost sur
       tests réparés). Mais A3 impose une représentation sensible à la
       direction d'effet avant tout minage de volume (sinon piège DW-37).
  E5 ← gaté par la vérification structurelle swe-smith (déjà FAITE : go, mais
       c'est une nouvelle campagne, pas une lecture de données)

Phase 3 (le plus cher, après tout le reste)
  E3 ← gates levés et chiffrés (22/08) ; fenêtre v49 PROPOSÉE (33 tickets
       gelés, exécution Kimsufi) — scellage owner attendu ; pivot naturel
       après v46/A3 + v47/V3 (vérité par exécution, pas par embedding)
```

Correction de séquence actée en contre-expertise : le brouillon initial gatait
E1/E5 sur « E6 confirme la robustesse » — faux lien. E6 teste la robustesse
adversariale du modèle JS/TS actuel, ça ne dit rien sur l'exploitabilité de
données Python/Go (E5) ni sur où cibler la classe rare (E1, qui dépend d'E9).

## Fichiers et outils clés (déjà localisés, à réutiliser tel quel)

- Serveur MCP / modèle de transition : `latent-imagination/scripts/mcp/ghost_server.py`
  (source de vérité — pas la copie vendored `ghost-mcp/`)
- Harnais LLM-judge (gabarit pour E2) : `scripts/act2/w45_judge_run.py`,
  `w45_judge_metrics.py`, `w45_judge_prep.py` + prereg `governance/act2/window-v45-llm-judge-proposal.md`
- Garde-fou architecture : `tests/guards/test_no_judge.py` (à faire tourner après
  toute modification touchant risk_scan/compare_patches — vérifie que la
  proscription LLM-dans-la-boucle-de-décision tient)
- Données transition/classe rare : `data/landing/act2-pilot/transitions/v39-transitions.jsonl`
  — **GELÉ le 2026-08-22** (finding P0 de v46 : régénéré silencieusement le
  21/08 après le verdict v41, baseline persistance dérivée 0,8197→0,9083 sans
  changement des compteurs globaux). sha256 de référence :
  `a8b51943cb25b037a64fb7bf9f418abfa133bc0b6adb0e76c98950795383bdd4`
  (loggé `data/release-store/prereg-ledger.jsonl`, type `data-freeze`). **Tout
  arm futur qui prétend utiliser « la même population » doit vérifier ce hash
  avant calcul et HALT sinon** — même discipline que le contrôle positif P0.
- Modèle de transition SERVI (copie locale du nœud, 2026-08-21) :
  `data/landing/act2-pilot/transition-model-served.npz` (1540 dims, λ 0.01,
  seuil Youden 0.0190, isotonic 703 pts)
- E4 final : `scripts/act2/w45_ece.py` + `arm-artifacts/arm-v45-e4-ece-final-2026-08-21.json`
- Fenêtre E6 : `governance/act2/window-v46-e6-adversarial-transition-proposal.md`
- Stock RED-GREEN pour E1/E3 : `data/landing/act2-pilot/night-harvest/{kimi,qwen,omniroute,...}/{verified,discovered}.json`
- Pool Python/Go pour E5 : `data/landing/swe-smith-trajectories/smith-matched-full/matched-items.json`
  (18 547 patches single-shot) + `data/landing/swe-smith-tasks/smith-tasks-v1/task-statements.json`
- Ledger machine-readable : `data/release-store/prereg-ledger.jsonl` + `governance/act2/arm-artifacts/*.json`
- Journal narratif : `_bmad-output/implementation-artifacts/deferred-work.md` (DW-64 pointe ici)

## Vérification / critère de clôture par expérience

Toutes réutilisent le gabarit déjà pratiqué dans ce ledger (prereg gelé avant tout
appel → grille de décision scellée type G1/G2/G3 → verdict horodaté dans
`arm-artifacts/`) :

- **E4** : ECE juge vs ECE Ghost (0,0205) — clôture par un simple delta chiffré. **Fait.**
- **E9** : nombre de cas structurés « juge a raison, Ghost a tort » ≥ un seuil à
  prédéfinir (ex. ≥5, cohérent avec la règle min-class déjà utilisée ailleurs, DW-16).
- **E8** : nombre d'appels LLM évitables sur les étapes déjà groundées ;
  seuil à fixer avant de lancer (discipline pré-registration).
- **E6** : taux d'effondrement de `predict_transition()` sur les quasi-diffs
  adversariaux vs taux sur les cas normaux — grille à sceller avant de construire
  les cas (jamais de seuil choisi après coup).
- **E2** : même grille G1/G2/G3 que v45, appliquée à l'axe per-test, décision sur
  Jaccard.
- **E1** : amélioration du Jaccard sur le sous-ensemble ciblé par E9 vs le modèle
  servi actuel.
- **E5** : AUC/Jaccard du modèle transition ré-entraîné ou testé zero-shot sur les
  trajectoires Python/Go générées vs persistance naïve sur cette même population.
- **E3** : taux de tickets où le blâme localisé identifie correctement le hunk
  responsable (vérité = ré-exécution réelle des tests, jamais un avis de modèle).
