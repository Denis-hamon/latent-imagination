#!/usr/bin/env python3
"""P14 — table {instance_id: test_cmd, log_parser}, gelee a part de la selection.

Fenetre `governance/act2/window-p14-variance-proposal.md`. Zero appel LLM.

Pourquoi un fichier separe : `test_cmd` vit dans `install_config` du dataset
amont, pas dans la selection. Le geler a part evite de toucher au sha256 de la
selection scellee — meme convention qu'en P12.

Usage : .venv/bin/python scripts/act2/p14_testcmd.py
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / "py-p14"
R = "hf://datasets/nebius/SWE-rebench/data/*.parquet"


def main() -> int:
    sel = json.loads((D / "p14-selection.json").read_text())
    ids = [s["instance_id"] for s in sel]
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("CREATE TABLE want(instance_id VARCHAR)")
    con.executemany("INSERT INTO want VALUES (?)", [(i,) for i in ids])
    rows = con.execute(f"""
        SELECT DISTINCT e.instance_id, e.install_config.test_cmd,
               e.install_config.log_parser
        FROM '{R}' e JOIN want w USING (instance_id)
    """).fetchall()
    tab = {i: {"test_cmd": c, "log_parser": p} for i, c, p in rows}
    manquants = [i for i in ids if i not in tab]
    # un `test_cmd` manquant ferait tomber la campagne entiere sur une KeyError
    # au milieu du rejeu : on le veut ici, pas a la 90e instance.
    if manquants:
        raise SystemExit(f"ECHEC : {len(manquants)} instances sans test_cmd : {manquants[:10]}")
    f = D / "p14-testcmd.json"
    f.write_text(json.dumps(tab, ensure_ascii=False, indent=1))
    print(f"{len(tab)} instances · {len({v['test_cmd'] for v in tab.values()})} commandes distinctes")
    print(f"ecrit : {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
