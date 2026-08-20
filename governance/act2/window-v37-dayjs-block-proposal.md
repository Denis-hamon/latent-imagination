# Fenêtre v37 — extension de la recette v36 au bloc dayjs (45 instances vérifiées)

v36 a établi la référence interne : 88 % de résolution (15/17) sur le bloc
vue avec Qwen3.8 max_tokens 65536, boucle cumulée. v37 teste la GÉNÉRALISATION
de la recette sur un second repo (dayjs, 45 instances vérifiées RED→GREEN
avec le harness officiel : matrice 4 TZ + noms suite:test, débloqué cette nuit).

## Protocole gelé

Mécanisme v36 identique (état cumulé, code courant réel, feedback 1600 chars,
consigne diff-seul, LI_MAX_TOKENS=65536, Qwen seul, ≤4 tours). Population :
instances dayjs vérifiées (verified-mswb.json du repo iamkun__dayjs), filtre
DW-52 src ≤ 1200 lignes ; cap 200 appels.

## Grille scellée

- R1 : resolution rate ≥ 60 % des instances retenues (barre plus basse que
  v36 : repo jamais vu par le modèle, jest au lieu de vitest, TZ multiples —
  test de généralisation, pas de pic) ;
- R2 : apply rate ≥ 45 % ;
- R3 : ≤ 200 appels.
R1 ET R2 ⇒ la recette généralise hors vue ; échec ⇒ la recette est
spécifique à vue/vitest et l'extension demande de l'adaptation par repo.

---

## FERMETURE — 2026-08-20 : **GRILLE 3/3 FRANCHIE — GÉNÉRALISATION CONFIRMÉE**

- **R1 : 39/43 instances dayjs résolues = 91 %** (≥60 % ✓✓) ;
- **R2 : apply 54/64 = 84 %** (≥45 % ✓✓) ;
- **R3 : 64/200 appels** (68 % sous le cap ✓) ;
- finish_reason=length : 7/64 (11 %) à 65k tokens — troncature marginale ;
- 4 irréductibles sur 43 (9 %).

**La recette v36 généralise AU-DELÀ de son repo d'origine** : vitest→jest,
TS→JS, environnement multi-TZ, fichiers ≤992 lignes, Qwen3.8 seul. Le score
combiné sur les deux blocs vérifiés sur notre hôte :
vue 15/17 (88 %) + dayjs 39/43 (91 %) = **54/60 = 90 %**.

Échelle de progression nocturne : 50 % (one-shot) → 65 % (boucle v32, troncature)
→ 82 % (v35, 40k tokens) → 88 % (v36, 65k, vue) → **91 % (v37, 65k, dayjs)**.
