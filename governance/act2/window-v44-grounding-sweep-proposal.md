# Fenêtre v44 — grounding sweep périodique (flywheel sans humain)

Item 3 validé par l'owner : alimentation régulière du flywheel par des
sessions produit automatisées (boucle product_session) sur le stock de
tickets vérifiés, sans intervention humaine.

## Protocole gelé

- rotation : file des tickets vérifiés non joués / non résolus (vue 7 restants,
  dayjs re-vérifiés, puis stock miné kimi/qwen/epv) ; un ticket par sweep ;
- boucle = product_session.py inchangé (risk_scan → compare_patches colonnes
  → exécution réelle → report_outcome groundé vitest) ;
- solveur : Qwen3.8 si répond sous 580 s, sinon DeepSeek-V4-Pro (fallback
  automatique sur timeout, disclosé par issue) ; max 3 tours ;
- PLAFOND : ≤ 20 appels LLM / jour (compteur calendrier dédié) ;
- timer : launchd macOS toutes les 6 h (machine allumée requis — disclosure :
  machine éteinte = pas de sweep, pas de perte de données).

## Livraison (fenêtre permanente de SERVICE, pas de mesure)

- issues groundées dans mcp-log.jsonl → collect flywheel nocturne ;
- sessions archivées (product-session-*.json) ;
- PAS de grille de performance : la métrique = volume groundé (rapporté par
  sweep). Toute analyse d'efficacité = fenêtre séparée future (v46+).

## Interdits

Aucun sweep sur pool servi / serving ; plafond 20/jour intangible sans
nouveau prereg ; pas de tuning du prompt pendant un sweep.

---

## MISE EN SERVICE — 2026-08-21

- Timer launchd chargé (com.latent-imagination.ghost-sweep, toutes les 6 h,
  copie versionnée dans ops/) ;
- test de bout en bout manuel : ticket queue → session produit → résolution
  vuejs__core-11761 au tour 1 (1 appel), compteur quotidien tenu, issue
  groundée (report_outcome) ;
- file de rotation : vue 7 + dayjs vérifiés ; les résolus sortent de la file
  (product-session-resolved-*.json), les joués-non-résolus passent en fin ;
- plafond 20 appels/jour actif (sweep-counter-v44.jsonl).
Premier sweep automatique au prochain intervalle du timer.
