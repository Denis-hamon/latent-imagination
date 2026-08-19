# Fenêtre v32 — boucle agentique test-in-loop cumulée sur Multi-SWE-bench vue (paradigme 2, owner validé)

Objectif produit : resolution rate sur instances réelles — le signal de
choix est l'EXÉCUTION RÉELLE des tests, jamais le world model. Zéro serving,
zéro modification produit Ghost.

## Baselines mesurées (figées avant la fenêtre, bloc vue v27)

- one-shot (tour 1 seul, v28) : 5/10 = 50 % ;
- boucle 4 tours à état reset (v28, 13/24 instances) : 11/13 = 85 % ;
- apply rate v28 : 28 % (le goulot).

## Protocole v32 (deltas scellés vs v28)

1. **État cumulé** : le worktree persiste entre les tours ; le diff du tour N
   est appliqué sur l'état courant (patch -p1 par hunk : les fichiers qui
   passent restent, les hunks rejetés sont signalés) ;
2. **prompt tour N>1 = code courant RÉEL** (les fichiers src tels qu'ils sont
   après les edits précédents), pas l'original fantasmé — attaque directe de
   l'hallucination de contexte (DW-52) ;
3. **feedback riche** : sorties de tests 1600 chars (assertions incluses),
   f2p encore rouges nominatifs, p2p cassés nominatifs, erreurs d'application
   réelles par hunk ;
4. 24 instances vue vérifiées RED→GREEN (v27), modèles Pro + Qwen, ≤4 tours,
   stop à convergence ; cap 192 appels.

## Grille scellée

- **R1 resolution rate** ≥ 70 % des 17 instances figées (≥1 modèle converge) —
  bien au-dessus du one-shot 50 % ; ≥ 85 % = niveau boucle v28 sur sous-bloc ;
- **R2 apply rate** ≥ 45 % des tours (v28 = 28 %) ;
- **R3 budget** ≤ 192 appels ;
- descriptif : appels par résolution, par modèle.
R1 ET R2 ⇒ fenêtre réussie (population figée 17, pas 24 : correction tracée
au ledger, cause = filtre DW-52 sur la taille src, identique à v28) ; publication du resolution rate comme référence
interne Multi-SWE-bench-vue ; données (diffs par tour + issues) versées au
stock trajectoires (paradigme 2 = aussi une source de données labelées).

## Interdits

Le world model ne sélectionne pas ; pas de test exécuté plus d'une fois par
(tour, état) ; les 24 instances sont la population entière — aucune sélection
a posteriori.

---

## FERMETURE — 2026-08-19 : grille R1/R2 manquée, mais validation partielle du mécanisme

**Résultat final (3 modèles : Pro + Qwen + Nemotron remplacement d'env)** :
- resolution rate **11/17 = 65 %** (grille R1 ≥70 % : ÉCHEC, à 5 pts) ;
- apply rate global **35 %** (grille R2 ≥45 % : ÉCHEC, à 10 pts) ;
- 14 convergences, budget 123/192 appels.

**Par modèle (la décomposition instructive)** :

| modèle | tours | appliqués | apply rate | instances convergées |
|---|---|---|---|---|
| DeepSeek-V4-Pro | 57 | 30 | **53 %** | 5 |
| Qwen3.8 | 49 | 13 | 27 % | 9 |
| Nemotron-120B (rempl.) | 17 | **0** | **0 %** | 0 |

**Lecture honnête** — deux enseignements opposés :

1. **Le mécanisme v32 (état cumulé + prompt code-courant réel) VALIDE la
   mitigation DW-52 pour le bon modèle** : Pro passe de 28 % d'apply (v28,
   état reset) à **53 %** (+25 pts). L'hallucination de contexte recule quand
   le modèle lit le code courant réel au lieu de le réimaginer. C'est le
   résultat positif de la fenêtre.

2. **Le resolution rate plafonne à 11/17 quel que soit le mécanisme** : v28
   (état reset, Pro+Qwen) résolvait déjà 11/13 instances couvertes ; v32
   retrouve les MÊMES 11 instances sur 17. Les 6 restantes sont hors de portée
   des modèles testés — la boucle ne les débloque pas. Le plafond est côté
   solveur (qualité des modèles), pas côté boucle. Nemotron (0 % apply) montre
   que tous les modèles ne produisent pas de diffs applicables.

**Conséquence produit** : la boucle test-in-loop est un **multiplicateur
d'efficacité** (meilleur apply → moins d'appels gaspillés), pas un
**débloqueur de résolution** sur les instances dures. Pour monter le
resolution rate il faut soit de meilleurs solveurs (modèles frontier), soit
accepter le plafond des modèles internes.

Aucun serving modifié. Données (diffs par tour) archivées dans replay-v32/.
