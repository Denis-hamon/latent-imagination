"""P16 — selection PAR LE TYPE DE DEPOT, a langage constant.

Fenetre : `governance/act2/window-p16-confondu-proposal.md`, SCELLEE le
2026-08-31 avant toute selection. Zero appel LLM.

LA QUESTION. Langage et type de depot sont parfaitement confondus sur toute la
campagne : w46 (JS/TS) n'a ete teste que sur un framework, `vuejs/core`, ou il
marche (p = 0,0198 sur 54 paires) ; P14 (Python) que sur des bibliotheques et un
outil CLI, ou il echoue. Aucune mesure existante ne dit lequel des deux facteurs
explique quoi.

P16 fait varier le TYPE DE DEPOT a langage constant, en Python, ou le materiel
existe sans un appel LLM : un bras FRAMEWORK (textual, starlette, tornado,
falcon) contre un bras BIBLIOTHEQUE (tox, streamlink, pennylane, wemake).

REGLE INCHANGEE. Meme predicat de variance que P14 (`n >= 4 AND 0 < r < n`),
memes plafonds K=4 / MAX_TRAJ=2 / MAX_DECLARED=18, meme temoin de fidelite.
SEULE LA COMPOSITION EN DEPOTS CHANGE, pour que P16 soit un A/B propre.

Usage : .venv/bin/python scripts/act2/p16_select.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / "py-p16"
T = "hf://datasets/nebius/SWE-rebench-openhands-trajectories/trajectories.parquet"
R = "hf://datasets/nebius/SWE-rebench/data/*.parquet"
# DEUX BRAS, geles par `governance/act2/window-p16-confondu-proposal.md` AVANT
# toute selection. Le facteur qui varie est le TYPE DE DEPOT, a langage constant.
FRAMEWORK = ("Textualize/textual", "encode/starlette",
             "tornadoweb/tornado", "falconry/falcon")
BIBLIO = ("tox-dev/tox", "streamlink/streamlink", "PennyLaneAI/pennylane",
          "wemake-services/wemake-python-styleguide")
# Les trois depots de P14 sont EXCLUS : les reutiliser rendrait le bras
# bibliotheque non independant d'un resultat deja connu.
EXCLUS_P14 = ("tobymao/sqlglot", "python-pillow/Pillow", "iterative/dvc")
REPOS = FRAMEWORK + BIBLIO
BRAS = {r: "framework" for r in FRAMEWORK} | {r: "biblio" for r in BIBLIO}
assert not (set(REPOS) & set(EXCLUS_P14)), "un depot de P14 s'est glisse dans P16"
K = 4              # tours par trajectoire = le maximum observé dans w46
MAX_DECLARED = 18  # idem : nombre maximal de tests déclarés d'une instance w46
MAX_TRAJ = 2       # trajectoires par instance (w46 : médiane 1, max 3)


def image_of(instance_id: str, docker_image: str | None) -> str:
    if docker_image:
        return docker_image
    org, rest = instance_id.split("__", 1)
    return "swerebench/sweb.eval.x86_64.{}_1776_{}".format(org, rest).lower()


def _p14_ids() -> set:
    """Recoupement avec P14 : il doit etre NUL. S'il ne l'est pas, un depot de
    P14 s'est glisse dans P16 et le bras bibliotheque n'est plus independant du
    resultat deja connu."""
    p = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / "py-p14" / "p14-selection.json"
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
    par_bras = {}
    for r, c in vent.items():
        par_bras[BRAS[r]] = par_bras.get(BRAS[r], 0) + c
    print(f"etude : {len(cand)} instances a issue mixte")
    print("  ventilation par depot :")
    for r, c in sorted(vent.items(), key=lambda x: -x[1]):
        print(f"    {r:44s} {c:3d}  [{BRAS[r]}]")
    print(f"  ventilation par BRAS : {par_bras}")
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
            "bras": BRAS[repo],
        })
    print(f"instances écartées (hors gabarit) : {len(ecartees)} {[e['instance_id'] for e in ecartees]}")
    f = D / "p16-selection.json"
    f.write_text(json.dumps(sel, ensure_ascii=False, indent=1))
    digest = hashlib.sha256(f.read_bytes()).hexdigest()
    (D / "p16-selection-freeze.json").write_text(json.dumps({
        "file": f.name, "sha256": digest, "n_instances": len(sel),
        "turns_per_trajectory": K, "max_trajectories": MAX_TRAJ,
        "max_declared": MAX_DECLARED, "ecartees": ecartees,
        "repos": list(REPOS), "bras_framework": list(FRAMEWORK),
        "bras_biblio": list(BIBLIO), "exclus_p14": list(EXCLUS_P14),
        "ventilation_par_bras": par_bras, "regle": "ETUDE n>=4 et 0<r<n (issue mixte garantie) ; TEMOIN n>=4 et r==n, 20 premieres",
        "n_temoin": len(temoin), "ventilation_etude_par_depot": vent,
    }, indent=1, ensure_ascii=False) + "\n")
    etude = [x for x in sel if not x["temoin"]]
    rec = len({x["instance_id"] for x in etude} & _p14_ids())
    print(f"population d'ETUDE : {len(etude)} instances · recoupement avec P14 : {rec}")
    if rec:
        raise SystemExit(f"ECHEC : {rec} instance(s) de P14 dans P16 — bras non independant")
    ntraj = sum(len(s["trajectories"]) for s in sel)
    paires = sum(len(s["FAIL_TO_PASS"]) * (K - 1) * len(s["trajectories"]) for s in sel)
    print(f"sha256 {digest}")
    print(f"{len(sel)} instances · {ntraj} trajectoires · {ntraj*(K-1)} paires de tours "
          f"-> {paires} paires test x tour")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
