"""P12 — les gates D1..D5, lus sur le rejeu.

Un tour v39 = un patch COMPLET régénéré depuis le parent. Une transition est
donc une paire de tours consécutifs (a,b) DANS UNE MÊME trajectoire, et une
ligne du corpus est un couple (transition, test déclaré).

  persist = 1  le test déclaré était déjà rouge au tour a
  y       = 1  le test déclaré est rouge au tour b

Le script tourne sur un rejeu PARTIEL sans mentir : il imprime toujours
combien d'instances il a réellement lues.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / "py-p12"
SEL = {x["instance_id"]: x for x in json.loads((D / "p12-selection.json").read_text())}


def main() -> int:
    files = sorted((D / "p12-replay").glob("*.json"))
    lignes, tours, insts, trajs = [], [], set(), 0
    n_instables, n_non_obs, n_non_conf, n_non_parse = 0, 0, 0, 0
    mesurees = []
    res_mesure, res_amont, accord = 0, 0, 0
    rangs = []   # position du 1er tour vert dans la trajectoire, normalisée

    for f in files:
        d = json.loads(f.read_text())
        iid = d["instance_id"]
        insts.add(iid)
        n_instables += len(d.get("instables") or [])
        decl = set(SEL[iid]["FAIL_TO_PASS"])

        for traj in d["trajectories"]:
            trajs += 1
            # Un tour n'entre dans le corpus que s'il a été MESURÉ : patch
            # réellement dans l'arbre (`applied`), sortie pytest parsée, et
            # tous les tests déclarés effectivement observés.
            ok = []
            for t in traj:
                # L'ordre compte : un tour non appliqué n'a JAMAIS été exécuté,
                # donc il n'a pas de `parsed`. Le tester d'abord le comptait
                # comme un échec de mesure au lieu d'un échec d'application.
                if not t.get("applied"):
                    n_non_conf += 1
                    continue
                if not t.get("parsed"):
                    n_non_parse += 1
                    continue
                if t.get("declares_non_observes"):
                    n_non_obs += 1
                    continue
                ok.append(t)

            verts = []
            for t in ok:
                fail = set(t["failed_all"])
                # « vert » = aucun test déclaré rouge ET aucun autre rouge. Ne
                # PAS comparer à `p2p` par égalité d'identifiant : les ids
                # tronqués par l'amont sont réparés à l'exécution, et le nom
                # observé diffère alors de celui de la sélection. La campagne
                # n'exécute que F2P ∪ P2P : tout rouge hors déclarés EST un P2P.
                vert = not fail
                verts.append(vert)
                res_mesure += vert
                res_amont += bool(t.get("resolved_upstream"))
                accord += (vert == bool(t.get("resolved_upstream")))
                tours.append(t)
            if verts:
                mesurees.append(traj)
                if any(verts):
                    rangs.append(verts.index(True) / max(1, len(verts) - 1))

            for a, b in zip(ok, ok[1:]):
                ra, rb = set(a["failed_all"]), set(b["failed_all"])
                for test in sorted(decl):
                    lignes.append({"persist": int(test in ra), "y": int(test in rb)})

    n = len(lignes)
    persist0 = sum(1 for r in lignes if r["persist"] == 0)
    y1 = sum(1 for r in lignes if r["y"] == 1)
    nt = len(tours)
    total_tours = n_non_parse + n_non_conf + n_non_obs + nt

    def pct(a, b): return 100.0 * a / b if b else 0.0

    print(f"REJEU LU : {len(insts)}/154 instances · {trajs} trajectoires · {nt} tours retenus")
    print(f"  tours écartés : {n_non_conf} non conformes · {n_non_parse} non parsés · "
          f"{n_non_obs} test déclaré non observé  (sur {total_tours})")
    print(f"  parents instables (double passe) : {n_instables}")
    print()
    print(f"D1 volume        {n} paires test×tour · {len(insts)} instances"
          f"    {'OK' if n >= 700 and len(insts) >= 70 else 'NON'}   (≥700 · ≥70)")
    print(f"D2 résolution    {pct(res_mesure, nt):.1f} %   mesuré"
          f"    {'OK' if pct(res_mesure, nt) >= 70 else 'NON'}   (≥70 %)")
    print(f"     amont       {pct(res_amont, nt):.1f} %   étiqueté · accord mesuré↔amont "
          f"{pct(accord, nt):.1f} %")
    print(f"D3 persist=0     {pct(persist0, n):.1f} %"
          f"    {'OK' if pct(persist0, n) >= 80 else 'NON'}   (≥80 %)")
    print(f"D4 y=1           {pct(y1, n):.1f} %   ({y1} positifs)"
          f"    {'OK' if 3 <= pct(y1, n) <= 15 else 'NON'}   (3–15 %)")
    print(f"D5 intégrité     {pct(nt, total_tours):.1f} %"
          f"    {'OK' if pct(nt, total_tours) >= 90 else 'NON'}   (≥90 %)")
    if rangs:
        print()
        print(f"position du 1er tour vert (0 = déjà vert au tour 1) : médiane {statistics.median(rangs):.2f}"
              f" · trajectoires mesurées jamais vertes {len(mesurees) - len(rangs)}/{len(mesurees)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
