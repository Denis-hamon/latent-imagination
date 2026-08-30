"""P14 — selection PAR LA VARIANCE DE LABEL.

Fenetre : `governance/act2/window-p14-variance-proposal.md`. Zero appel LLM.

DEFAUT CORRIGE. `p12_select.py` exigeait `r/n >= 0.75` : au moins 75 % des
trajectoires d'une instance devaient etre resolues. Le gate D2 — concu comme un
controle de FIDELITE DU HARNAIS — etait applique comme un FILTRE DE POPULATION.
Resultat mesure : 81 echecs sur 1692 trajectoires (5 %), alors que le gisement
en offre 46 %. La metrique ne consomme que les instances a ISSUE MIXTE ; le
rendement de P12 etait de 18 %, celui des instances a blocs melanges de 85 %.

REGLE P14 : `n >= 4 AND r > 0 AND r < n`. Chaque instance retenue a donc AU
MOINS UNE reussite ET AU MOINS UN echec. Meme profondeur, memes depots, memes
plafonds que P12 : SEULE LA SELECTION CHANGE, pour que P14 soit un A/B propre.

LES 209 INSTANCES JAMAIS RESOLUES SONT EXCLUES, et c'est symetrique : un test
declare rouge a tous les tours ne produit que des y=1, donc aucune paire
(positif, negatif) intra-instance. Sterile dans l'autre sens.

TEMOIN DE FIDELITE : 20 instances `r == n`, marquees `temoin: true`, sur
lesquelles seules D2 sera lu. Elles ne font pas partie de la population d'etude.

Usage : .venv/bin/python scripts/act2/p14_select.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / "py-p14"
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


def _p12_ids() -> set:
    """Recoupement avec P12 : s'il est eleve, le predicat n'a pas ete inverse."""
    p = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / "py-p12" / "p12-selection.json"
    if not p.is_file():
        return set()
    d = json.loads(p.read_text())
    d = d if isinstance(d, list) else list(d.values())[0]
    return {x["instance_id"] for x in d}


def main() -> int:
    D.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(f"""CREATE TABLE agg AS SELECT instance_id, any_value(repo) repo,
        count(*) n, sum(resolved) r FROM '{T}' WHERE repo IN {REPOS} GROUP BY instance_id""")
    # ETUDE : issue mixte garantie — au moins une reussite ET au moins un echec.
    cand = con.execute(
        "SELECT instance_id, n FROM agg WHERE n >= 4 AND r > 0 AND r < n ORDER BY instance_id"
    ).fetchall()
    # TEMOIN de fidelite du harnais : 20 instances toujours resolues, tirage
    # deterministe. D2 ne sera lu QUE sur elles.
    temoin = con.execute(
        "SELECT instance_id, n FROM agg WHERE n >= 4 AND r = n ORDER BY instance_id LIMIT 20"
    ).fetchall()
    navail = {i: k for i, k in cand + temoin}
    est_temoin = {i for i, _ in temoin}
    vent = dict(con.execute("""SELECT any_value(repo), count(*) FROM agg
        WHERE n >= 4 AND r > 0 AND r < n GROUP BY repo""").fetchall())
    # correctif de protocole n0 de P13 : ventiler PAR DEPOT avant de rejouer.
    print(f"etude : {len(cand)} instances a issue mixte · ventilation par depot {vent}")
    print(f"temoin de fidelite : {len(temoin)} instances toujours resolues")

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
            "temoin": iid in est_temoin,
        })
    print(f"instances écartées (hors gabarit) : {len(ecartees)} {[e['instance_id'] for e in ecartees]}")
    f = D / "p14-selection.json"
    f.write_text(json.dumps(sel, ensure_ascii=False, indent=1))
    digest = hashlib.sha256(f.read_bytes()).hexdigest()
    (D / "p14-selection-freeze.json").write_text(json.dumps({
        "file": f.name, "sha256": digest, "n_instances": len(sel),
        "turns_per_trajectory": K, "max_trajectories": MAX_TRAJ,
        "max_declared": MAX_DECLARED, "ecartees": ecartees,
        "repos": list(REPOS), "regle": "ETUDE n>=4 et 0<r<n (issue mixte garantie) ; TEMOIN n>=4 et r==n, 20 premieres",
        "n_temoin": len(temoin), "ventilation_etude_par_depot": vent,
    }, indent=1, ensure_ascii=False) + "\n")
    etude = [x for x in sel if not x["temoin"]]
    rec = len({x["instance_id"] for x in etude} & _p12_ids())
    print(f"population d'ETUDE : {len(etude)} instances · recoupement avec P12 : {rec}")
    ntraj = sum(len(s["trajectories"]) for s in sel)
    paires = sum(len(s["FAIL_TO_PASS"]) * (K - 1) * len(s["trajectories"]) for s in sel)
    print(f"sha256 {digest}")
    print(f"{len(sel)} instances · {ntraj} trajectoires · {ntraj*(K-1)} paires de tours "
          f"-> {paires} paires test x tour")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
