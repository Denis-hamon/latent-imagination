# Window COVERAGE-NEXTJS-TS — DRAFT (non pré-enregistrée, aucune dépense approuvée)

Status: DRAFT 2026-08-15 — piste de couverture enregistrée pour plus tard.
NE PAS exécuter sans : (1) promotion en pré-enregistrement complet (même
discipline que window-gen-families-v1.md : valeurs gelées, envelope budgétaire,
ancrage), et (2) approbation owner de l'enveloppe de dépense.

## Pourquoi ce draft existe (mesuré, pas spéculé)

Log serveur GHOST v9 au 2026-08-15 (23 risk_scans réels, tau = 0.1547) :

| sollicitation | familles | conf | décision |
|---|---|---|---|
| Qwen / BMAD epic-7 (×5) | packages/gate, packages/prereg, governance/ | 0.007–0.039 | abstain ×5 |
| Claude / Acre Next.js (×6) | apps/front, apps/api (monorepo TS) | 0.011–0.164 | abstain ×5, low_risk ×1 (borderline, conf 0.164 juste > tau) |
| Claude / cloner (×1) | m.py | 0.041 | abstain ×1 |
| familles du pool (pyca__pyopenssl ×6, sonde ×5) | — | 0.178–0.236 | high_risk ×5, abstain ×6 |

Lecture : GHOST tranche sur les familles de bug-fix mono-repo avec signal de
test (les 60 du pool v9) et s'abstient sur **100 % du travail applicatif
réel récent** (11/11 requêtes TS-monorepo ou gouvernance). Le cas limite Acre
(conf 0.164, verdict rendu) montre que la frontière est géométrique, pas
nominale — mais c'est l'exception en bordure du régime calibré.

## Hypothèse à valider avant toute exécution

La géométrie actuelle est entraînée sur des diffs SWE-smith (bug-fix
mono-fichier/few-files, Python/Go majoritairement, signal F2P/P2P). Les diffs
Next.js/TS applicatifs (features multi-fichiers, types, composants, monorepo)
sont structurellement différents. Deux issues possibles pour une fenêtre :

1. **Extension de couverture** : ajouter des familles TS/Next.js AU POOL avec
   le même protocole (tâches → bug/patch → F2P/P2P via jest/vitest/playwright
   → mesure per-quota AVANT mix, poison-check < 0.65 AUC ext-only). Condition
   sine qua non : trouver/produire des tâches TS avec signal de test juge-free
   (le label doit rester re-derivable FR-3 — pas de verdicts juge).
2. **Non-couverture honnête** : si aucune source de tâches TS à signal de test
   n'est disponible dans les droits enregistrables, la bonne issue est
   d'étendre le diagnostic d'abstention (v0.4.0) pour que GHOST NOMME
   explicitement "famille TS/monorepo hors couverture" au lieu d'un abstain
   générique — pas de fausse couverture.

Le choix entre (1) et (2) est un acte de pré-enregistrement ultérieur, avec
sources.yaml registration préalable pour toute nouvelle source (droits,
licences).

## Ce qu'une exécution devra geler (checklist pré-enregistrement)

- [ ] Source(s) de tâches TS/Next.js avec signal de test (jest/vitest) et
      droits enregistrés dans sources.yaml (politique de licence existante :
      MIT/Apache/BSD/ISC/0BSD).
- [ ] Quotas par famille cible (forme s12/s14 : N tâches × 2 tirages).
- [ ] Modèle-auteur épinglé + prompt/extract class gelés (référence ou
      amendement documenté si la classe TS exige un extracteur distinct —
      attention : tout changement de classe d'extraction est une modification
      de l'instrument, à traiter comme tel).
- [ ] Enveloppe d'appels [ASSUMPTION], stop-at-cap, overspend = amendement.
- [ ] Mesure par quota AVANT mix dans le pool servi ; poison-check ;
      provenance strata distincte (jamais mélangée avant mesure).
- [ ] Fenêtre d'approbation owner + ancrage du document approuvé (comme
      gen-families-v1, cérémonie 9.3).

## Déclencheur de réexamen

Ce draft revient à l'ordre du jour quand l'une des conditions est remplie :
- le verdict Act III (épic 11) est rendu et un nouveau cycle de croissance du
  pool s'ouvre, OU
- la proportion de requêtes TS/monorepo dans le log GHOST dépasse la moitié
  des sollicitations réelles sur une fenêtre glissante (la couverture devient
  le facteur limitant mesuré de l'utilité de GHOST).

Owner de la décision : Denis. Gardien du draft : le ledger deferred-work.
