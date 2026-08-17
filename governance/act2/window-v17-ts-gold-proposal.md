# Fenêtre v17 — axe gold TS (proposition scellée, zéro appel LLM)

Constat : les 113 lignes TS du pool servi sont goal-free (comme 223/430),
alors que 264 tickets vérifiés (232 omniroute + 32 zod) portent fix_commit —
le diff de la vraie correction est sur disque. L'ancre v6-GOLD montre que
l'axe goal est le signal supervisé le plus riche mesuré (AUC jina 0.8315) ;
les lignes TS en sont privées. Levier n°1 du plan TS (owner: « ok go »).

## Population (figée à l'export)

Lignes harvest appliquées (y mesuré par exécution réel) dont le ticket a un
fix_commit, pour lesquelles le diff candidat est sur disque : omniroute + zod,
toutes fenêtres cumulées (v13 waves 1-4, v15-B draws 5-10, nuit). Synthétique
exclu de cet arm (manifest sans gold ; reconstruire via git = arm séparé).

## Protocole gelé

1. Export gold : pour chaque ligne, `git show fix_commit -- <src_files>` au
   format patch unifié (au parent du fix, jamais HEAD) = texte gold ;
2. Textes state/diff identiques bit-à-bit aux lignes harvest existantes
   (jamais reconstruits de mémoire) ;
3. Embeddings jina-v2-base-code (protocole ghost_server.embed strict),
   E_state, E_diff, E_goal ;
4. Mesure PAIRÉE sur la même population : AUC ext-LOAO axe goal
   (loao_energy cd vs cg, recette ancre v6) vs AUC cd-only (recette servie) ;
5. IC95 bootstrap 1000 sur la différence d'AUC.

## Grille de décision scellée

- AUC_goal ≥ AUC_cd + 0.05 ET borne basse IC95(diff) ≥ 0 ⇒ arm VALIDÉ :
  ouvre la fenêtre de reconstruction pool TS avec goal (v18, décision owner) ;
- sinon ⇒ CLOS : l'axe gold ne sépare pas les candidats TS mieux que cd seul.

## Interdits

Pas de gold reconstruit de mémoire ; pas de sélection de sous-population
post-mesure ; pas de mélange avec le pool servi avant grille ; le pool v12
reste servi quel que soit le résultat.

---

## FERMETURE — 2026-08-17 (grille franchie)

**VERDICT : VALIDÉ.** 312 lignes réelles (99 tickets, 163+/149−), golds =
diffs des vrais fix (git show fix_commit au parent, sur Kimsufi), zéro appel
LLM, embeddings jina protocole servi.

- AUC cd-only (recette servie f1 LOAO+report) : **0.5022** — la géométrie
  servie porte l'équivalent d'un tirage au hasard sur les tickets réels TS ;
- AUC axe goal (recette ancre v6 loao_energy+report) : **0.7408** ;
- Δ goal−cd : +0.2386, IC95 bootstrap 1000 : [+0.147, +0.322].

Deux runs invalides disclosés avant celui-ci (recette ad hoc inversée en
run1 ; bug de formule IC en run2 — verdict erroné détecté au contrôle de
vraisemblance, jamais rapporté). Artifact : arm-v17-ts-gold-mesure-2026-08-17.json.

**Conséquence (prereg) : ouvre la fenêtre v18 — reconstruction d'un pool TS
avec axe goal (les 312 lignes + golds, puis extension aux 264 tickets),
recalibration conforme par strate, décision owner.** Le pool v12 reste servi ;
rien n'est promu par cette fenêtre.
