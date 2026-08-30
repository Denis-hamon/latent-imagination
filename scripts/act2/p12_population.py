"""P12 — le rapport de population NON FILTRÉE, promis dans la fenêtre.

La sélection P12 retient les instances à >= 4 trajectoires ET taux de
résolution >= 0,75. Ce filtre FABRIQUE le régime, et la fenêtre le divulgue.
Encore faut-il rendre son effet lisible : ce script décrit la population des
mêmes dépôts SANS le seuil de résolution, pour qu'on voie ce qui a été écarté.

Aucune exécution de conteneur, aucun appel LLM : lecture du dataset amont.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / "py-p12"
T = "hf://datasets/nebius/SWE-rebench-openhands-trajectories/trajectories.parquet"
REPOS = ("tobymao/sqlglot", "python-pillow/Pillow", "iterative/dvc")


def main() -> int:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(f"""CREATE TABLE agg AS SELECT instance_id, any_value(repo) repo,
        count(*) n, sum(resolved) r, sum(resolved)*1.0/count(*) taux
        FROM '{T}' WHERE repo IN {REPOS} GROUP BY instance_id""")

    tout = con.execute("SELECT count(*), sum(n), sum(r) FROM agg").fetchone()
    q4 = con.execute("SELECT count(*), sum(n), sum(r) FROM agg WHERE n >= 4").fetchone()
    ret = con.execute("SELECT count(*), sum(n), sum(r) FROM agg "
                      "WHERE n >= 4 AND taux >= 0.75").fetchone()

    print("POPULATION DES 3 DÉPÔTS, SANS SEUIL DE RÉSOLUTION")
    for nom, (ni, nt, nr) in (("toutes instances", tout),
                              ("      >= 4 traj.", q4),
                              ("  + taux >= 0,75", ret)):
        print(f"  {nom} : {ni:4d} instances · {nt:6d} trajectoires · "
              f"résolution amont {100.0*nr/nt:5.1f} %")

    print()
    print("DISTRIBUTION DU TAUX DE RÉSOLUTION (instances à >= 4 trajectoires)")
    for lo, hi in ((0.0, 0.01), (0.01, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 1.01)):
        n, t = con.execute(
            "SELECT count(*), coalesce(sum(n),0) FROM agg WHERE n >= 4 "
            f"AND taux >= {lo} AND taux < {hi}").fetchone()
        marque = "  <- RETENU" if lo >= 0.75 else ""
        print(f"  [{lo:.2f} , {hi if hi <= 1 else 1.0:.2f}]  {n:4d} instances · "
              f"{t:5d} trajectoires{marque}")

    print()
    print("PAR DÉPÔT (instances à >= 4 trajectoires)")
    for repo, ni, nret, tx in con.execute(
            "SELECT repo, count(*), count(*) FILTER (WHERE taux >= 0.75), "
            "avg(taux) FROM agg WHERE n >= 4 GROUP BY repo ORDER BY repo").fetchall():
        print(f"  {repo:24s} {nret:3d}/{ni:3d} retenues · taux moyen {100*tx:5.1f} %")

    (D / "p12-population-non-filtree.json").write_text(json.dumps({
        "repos": list(REPOS),
        "toutes": {"instances": tout[0], "trajectoires": tout[1], "resolues": tout[2]},
        "min4traj": {"instances": q4[0], "trajectoires": q4[1], "resolues": q4[2]},
        "retenues": {"instances": ret[0], "trajectoires": ret[1], "resolues": ret[2]},
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
