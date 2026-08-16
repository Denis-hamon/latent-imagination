# Epic 13 — verdict des candidats géométrie family-invariant (2026-08-16)

Écrit APRÈS les trois mesures, contre les gates scellés 13.1
(ext-loao-candidate-gates-v1.md, commit 5e9a0ff) : marge transfert +0.05 sur la
baseline stricte 0.5477 (seuil 0.5977), home-guard in-family ≥ 0.6494,
tie → baseline, promotion prospective seulement.

## Résultats (mêmes folds, 0 appel, pool v10 gelé)

| candidat | ext-LOAO strict | in-family | transfert | home | issue |
|---|---|---|---|---|---|
| baseline (géométrie servie) | 0.5477 | 0.6694 | — | — | référence scellée |
| 13.2 AST-normalized diffs | 0.5276 | 0.6566 | ✗ (<0.5977) | ✓ | négatif publié |
| **13.3 adversarial probe** | **0.6719** | **0.6694** | **✓** | **✓** | **CANDIDATE enregistré** |
| 13.4 joint diff×trace | 0.4038 | 0.6694 | ✗ | ✓ | négatif publié |

## Décisions

1. **advprobe = CANDIDATE (enregistré, PAS promu).** Combinator gelé :
   projection linéaire 768→12, λ_adv=1.0, lr=1e-3, epochs=300, seed=20260805,
   entraînement LOFO par famille (artefact
   `arm-artifacts/ext-loao-candidate-advprobe-v10.json`). La géométrie servie
   (v10) n'est PAS modifiée — aucun swap dans cet épic.
2. **Validation prospective pré-enregistrée** : le candidat sera évalué sur les
   lignes JAMAIS VUES de la prochaine fenêtre de croissance (Épic 14 TS/Next.js
   ou prochain lot flywheel promu) : ext-LOAO ≥ 0.5977 sur ces lignes seules,
   home-guard inchangée, mêmes gates amendment-only. Franchissement sur données
   jamais vues ⇒ passage en phase de promotion (avec gate régime 9.1 +
   re-mesure de calibration servant) ; échec ⇒ publié comme les deux autres.
3. **13.2 et 13.4 publiés avec la même discipline** (artefacts dans
   arm-artifacts/, même layout) : abstraire la texture des identifiants
   n'ajoute pas de signal transférable ; l'espace joint diff×trace est tué par
   sa propre asymétrie de serving (la requête n'a jamais de trace → les lignes
   avec trace s'éloignent dans des dimensions que la requête ne peut pas
   atteindre ; mesuré 0.4038, sous le hasard — l'asymétrie est le mécanisme,
   pas le bruit).
4. **Lecture** : le signal transférable hors-famille existe (0.5477 → 0.6719)
   quand on force l'espace à oublier la famille à capacité bornée (9.2k params)
   sans oublier l'issue. La croissance du pool seule (Epic 10) n'avait pas
   suffi ; l'invariance apprise oui — sur le pool qui l'a testée, d'où la
   validation prospective obligatoire.

Aucun amendement des gates n'a été nécessaire ; aucun réglage post-mesure.

## MISE À JOUR 2026-08-16 (soir) — validation certifiable échouée

La première population TS CERTIFIABLE (coverage-ts-v5 : 7 pos / 6 neg, les deux
classes ≥ 5) a mesuré le candidat advprobe à **AUC 0.4286 < 0.5977 → non
franchie**. Les trois validations antérieures (0.60 v2 / 0.85 v3 / 0.73 v4)
portaient toutes sur des populations dégénérées (1-3 négatifs) où l'AUC n'a
quasiment aucun pouvoir discriminant : elles n'étaient PAS prédictives. 

Statut mis à jour : advprobe **RÉTROGRADÉ** de « CANDIDATE en validation » à
« évidence non confirmée » — archivé avec toutes ses mesures (le candidat n'est
pas supprimé : une future population certifiable pourra le re-tester contre la
même gate gelée, mais rien n'est dû). C'est la règle classe-min qui a protégé
le pool : sans elle, trois « validations » dégénérées auraient suffi à promouvoir
un candidat qui échoue au premier test réel.

**Confirmation sur population agrégée (même jour)** : pooled 63 lignes
(51 pos/12 neg, 4 repos — voir arm-artifacts/ts-dedicated-geometry-memo-2026-08-16.md)
→ advprobe 0.4951 < 0.5977, second échec certifiable consécutif. Le candidat
est définitivement clos sur l'état actuel des évidences.
