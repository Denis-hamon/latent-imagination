# Window NIGHT-HARVEST-v1 — collecte tickets réels (pré-enregistrement v1)

Status: APPROVED 2026-08-17 — mandat owner « plan 8h d'amélioration continue
par nouvelle data » + validation démo ticket-réel #8331 (6a00903).

## Hypothèse mesurée

L'historique git réel d'OmniRoute (6905 commits, tests numérotés par issue)
fournit des tickets SWE-bench-style à vérité terrain objective (buggy = parent
du fix, tests = suites du fix, fix humain = ground truth). La collecte nuit
doit produire pooled5 : population TS élargie, équilibrée, mesurée par batch.

## Portée

- Source principale : OmniRoute @ e646fe84 (blobless-fetch historique fait) ;
  extension mi-nuit : zod + date-fns (fetch historique + adaptation mineur)
  SEULEMENT si OmniRoute fournit < 20 tickets éligibles.
- Filtres d'éligibilité (pré-enregistrés) : fix mono/multi-fichier <= 3
  fichiers source open-sse/**, diff source <= 250 lignes, fichiers <= 600
  lignes chacun (leçon démo : gros contexte = no-diff 5/8), tests unitaires
  purs, double contrôle RED (F2P >= 2 cassés au parent) puis GREEN (tout vert
  au fix) — sinon ticket rejeté journalisé.
- Auteurs : DeepSeek-V4-Flash (principal, 4 tirages/ticket) ; ESCALADE
  pré-enregistrée : si batch 1 produit < 30 % de négatifs, batch 2+ passe à
  GLM-5.2-NVFP4 (3 tirages/ticket). L'auteur épinglé : DOWN (v10), exclu.

## Enveloppe [ratifiée par mandat 8h]

- Cap dur **500 appels auteurs** (compteur global journalisé append-only,
  le refus-au-501e est codé comme en genfam S14) ;
- infra-stop >= 8 erreurs endpoint consécutives ; abort batch si no-diff > 60 % ;
- quarantaine <= 10 % par batch sinon le batch est archivé-diagnostiqué ;
- commits incrémentaux toutes les ~2 heures ; rapport de réveil en tête de bilan.

## Mesure (par batch + finale)

Poison ext-LOAO + AUC/IC bootstrap sur pooled5 (jina, protocole identique
pooled4) ; AUC par famille-repo ; DW-37 : aucune strate sparse n'est agrégée
en silence ; analyse de puissance vers critères de mix.

## Critères au réveil (pré-enregistrés, décision owner ensuite)

- MIX-READY : pooled5 passe poison >= 0.65 (jina) ET IC95 lo > 0.60 ET >= 2
  familles TS à >= 5 négatifs chacune => cérémonie v12 préparée (non servie).
- SINON : bilan chiffré + dimensionnement fenêtre suivante ; serving v0.7.0
  (pool v11) INTACT toute la nuit.

## Interdits

Aucun serving modifié ; aucun seuil amendé en cours de nuit ; aucun ticket
hors filtres ; le texte des fix solutions jamais inclus dans les prompts.
