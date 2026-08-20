# Fenêtre v41 — re-jugement de l'arm transition séquentielle sur données densifiées

Suite approuvée par l'owner (« densifier d'abord »). v39 a VALIDÉ le signal
séquentiel sur 72 transitions / 152 paires ; v40 densifie. Re-jugement sur
l'inventaire complet à la fermeture de v40.

## Population (figée à l'ouverture effective = à la fermeture de v40)

`transitions/v39-transitions.jsonl` régénéré à la fermeture de v40 : toutes
fenêtres v32→v40 incluses. Aucun ajout posterior.

## Protocole (identique v39, mot pour mot)

Features [E_diff_{t+1}‖E_test‖cos‖persist‖frac_rouges_t‖tour], logistique
L2 λ=1e-2 LBFGS 150, LOO par TRAJECTOIRE (instance+modèle), baseline
persistance même pipeline features [persist]. Recette node identique.

## Grille scellée (identique v39)

- T1 : AUC paire LOO-trajectoire modèle ≥ persistance + 0.03 ;
- T2 : Jaccard moyen (transitions à red_to non vide, seuil Youden du modèle)
  ≥ persistance + 0.05 ;
- T1 ET T2 ⇒ VALIDÉ : la fenêtre produit « évolution prédite des tests »
  devient proposable à l'owner (population réelle au moment du jugement) ;
- échec ⇒ le signal v39 était un artefact de petite population ; arm CLOS.

## Interdits

Pas de changement de features/seuils ; la population est celle de la
fermeture v40, pas une version cherry-pickée.

---

## FERMETURE — 2026-08-20 : **VALIDÉ (T1 ET T2)**

- T1 AUC paire LOO-trajectoire : **0.9931** vs persistance 0.8197 (Δ +0.173,
  seuil +0.03) ; T2 Jaccard moyen : **0.9333** vs 0.78 (Δ +0.153, seuil +0.05,
  n=25 transitions évaluées) ;
- le signal séquentiel se RENFORCE avec la densification (v39 : 0.9601/0.90 ;
  v41 : 0.9931/0.9333) — pas un artefact de petite population ;
- caveat scellé au verdict : les 30 labels positifs sont les mêmes qu'en v39
  (v40 n'a pas produit de transitions à red déclaré non vide) — la classe
  rare impose la prudence avant tout serving ;
- conséquence prereg : la fenêtre produit « évolution prédite des tests »
  est proposable — décision owner.
