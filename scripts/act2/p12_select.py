"""P12 — sélection GELÉE d'un corpus Python en sémantique v39.

Un tour = un patch COMPLET régénéré depuis le parent, comme dans w46 — et non
une édition incrémentale comme en P9. Le dataset amont fournit plusieurs
trajectoires indépendantes par instance : leurs `model_patch` respectifs sont
exactement cette suite de patchs complets. ZÉRO appel LLM.

Règles, mécaniques, fixées avant toute exécution :
 1. dépôts = les 3 de la sélection P9 (aucun nouveau choix de dépôt) ;
 2. instances ayant >= 4 trajectoires ET un taux de résolution >= 0,75 ;
 3. toutes les instances retenues, sans troncature (couper à 70 en ordre
    lexicographique éliminait la totalité de sqlglot) ;
 4. instances dont le nombre de tests déclarés dépasse le maximum de w46 (18)
    ECARTEES — jamais tronquées : tronquer déformerait l'instance, l'écarter
    dit simplement qu'elle n'a pas d'analogue dans le corpus de référence ;
 5. trajectoires = blocs consécutifs de 4 dans la liste triée par
    `trajectory_id` ; 2 blocs si l'instance a >= 8 trajectoires, sinon 1.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / "py-p12"
T = "hf://datasets/nebius/SWE-rebench-openhands-trajectories/trajectories.parquet"
R = "hf://datasets/nebius/SWE-rebench/data/*.parquet"
REPOS = ("tobymao/sqlglot", "python-pillow/Pillow", "iterative/dvc")
K = 4              # tours par trajectoire = le maximum observé dans w46
MAX_DECLARED = 18  # idem : nombre maximal de tests déclarés d'une instance w46
MAX_TRAJ = 2       # trajectoires par instance (w46 : médiane 1, max 3)


def image_of(instance_id: str, docker_image: str | None) -> str:
    if docker_image:
        return docker_image
    org, rest = instance_id.split("__", 1)
    return "swerebench/sweb.eval.x86_64.{}_1776_{}".format(org, rest).lower()


def main() -> int:
    D.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(f"""CREATE TABLE agg AS SELECT instance_id, any_value(repo) repo,
        count(*) n, sum(resolved) r FROM '{T}' WHERE repo IN {REPOS} GROUP BY instance_id""")
    cand = con.execute(
        "SELECT instance_id, n FROM agg WHERE n >= 4 AND r*1.0/n >= 0.75 ORDER BY instance_id"
    ).fetchall()
    navail = {i: k for i, k in cand}
    print(f"instances candidates : {len(cand)}")

    con.execute("CREATE TABLE want(instance_id VARCHAR)")
    con.executemany("INSERT INTO want VALUES (?)", [(i,) for i in navail])

    trajs = con.execute(f"""
        SELECT instance_id, trajectory_id, resolved, model_patch, rk FROM (
          SELECT t.instance_id, t.trajectory_id, t.resolved, t.model_patch,
                 row_number() OVER (PARTITION BY t.instance_id
                                    ORDER BY t.trajectory_id ASC) rk
          FROM '{T}' t JOIN want w USING (instance_id)
        ) WHERE rk <= {K * MAX_TRAJ} ORDER BY instance_id, rk
    """).fetchall()
    print(f"tours récupérés : {len(trajs)}")

    meta = {r[0]: r for r in con.execute(f"""
        SELECT DISTINCT m.instance_id, m.repo, m.base_commit, m.test_patch,
               m.FAIL_TO_PASS, m.PASS_TO_PASS, m.docker_image
        FROM '{R}' m JOIN want w USING (instance_id)
    """).fetchall()}
    print(f"métadonnées : {len(meta)}")

    par = {}
    for iid, tid, resolved, mp, rk in trajs:
        par.setdefault(iid, []).append(
            {"trajectory_id": tid, "resolved": int(resolved), "model_patch": mp})

    sel, ecartees = [], []
    for iid in navail:
        _, repo, base, tp, f2p, p2p, img = meta[iid]
        if len(f2p) > MAX_DECLARED:
            ecartees.append({"instance_id": iid, "n_declared": len(f2p),
                             "motif": f"plus de {MAX_DECLARED} tests déclarés (hors gabarit w46)"})
            continue
        blocs = []
        dispo = par[iid]
        for b in range(MAX_TRAJ if navail[iid] >= 2 * K else 1):
            tours = dispo[b * K:(b + 1) * K]
            if len(tours) == K:
                blocs.append([{**t, "turn": j + 1} for j, t in enumerate(tours)])
        sel.append({
            "instance_id": iid, "repo": repo, "base_commit": base,
            "docker_image": image_of(iid, img), "test_patch": tp,
            "FAIL_TO_PASS": sorted(f2p), "PASS_TO_PASS": list(p2p),
            "trajectories": blocs,
        })
    print(f"instances écartées (hors gabarit) : {len(ecartees)} {[e['instance_id'] for e in ecartees]}")
    f = D / "p12-selection.json"
    f.write_text(json.dumps(sel, ensure_ascii=False, indent=1))
    digest = hashlib.sha256(f.read_bytes()).hexdigest()
    (D / "p12-selection-freeze.json").write_text(json.dumps({
        "file": f.name, "sha256": digest, "n_instances": len(sel),
        "turns_per_trajectory": K, "max_trajectories": MAX_TRAJ,
        "max_declared": MAX_DECLARED, "ecartees": ecartees,
        "repos": list(REPOS), "regle": "n>=4 trajectoires et resolution>=0.75, ordre lexicographique",
    }, indent=1, ensure_ascii=False) + "\n")
    ntraj = sum(len(s["trajectories"]) for s in sel)
    paires = sum(len(s["FAIL_TO_PASS"]) * (K - 1) * len(s["trajectories"]) for s in sel)
    print(f"sha256 {digest}")
    print(f"{len(sel)} instances · {ntraj} trajectoires · {ntraj*(K-1)} paires de tours "
          f"-> {paires} paires test x tour")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
