"""P12 étapes 7 à 11 — exécution des patchs complets, vérité par exécution.

Un tour = le `model_patch` d'une trajectoire amont, appliqué tel quel sur le
parent. Rien n'est reconstruit : le contrôle d'intégrité porte sur l'APPLICATION
du patch, pas sur une égalité d'état. ZÉRO appel LLM.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p9_replay import (  # noqa: E402
    sh, run_tests, is_brouillon, patch_files, normalize_diff, test_paths,
)

ROOT = Path(__file__).resolve().parents[2]
# Corpus pilotable par variable d'environnement : P14 rejoue EXACTEMENT le meme
# harnais (les cinq correctifs compris) sur une selection differente. Dupliquer
# le fichier aurait fait diverger les correctifs en silence.
CORPUS = os.environ.get("LI_CORPUS", "p12")
D = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / f"py-{CORPUS}"
OUT = D / f"{CORPUS}-replay"


def cname(iid: str) -> str:
    return "p12-" + re.sub(r"[^a-zA-Z0-9_.-]", "-", iid)


def load(iid: str) -> dict:
    # `test_cmd` vit dans `install_config` en amont : il est gelé à part pour ne
    # pas toucher au sha256 de la sélection scellée.
    cmds = json.loads((D / f"{CORPUS}-testcmd.json").read_text())
    for s in json.loads((D / f"{CORPUS}-selection.json").read_text()):
        if s["instance_id"] == iid:
            return {**s, **cmds[iid]}
    raise SystemExit(f"instance absente de la sélection : {iid}")


def code_patch(mp: str) -> str:
    """Le patch privé des brouillons d'agent (`.openhands/**`, fichiers neufs
    de premier niveau). Ils polluent `diff_to`, qui est une entrée du modèle."""
    keep = []
    for b in re.split(r"(?m)^diff --git ", mp or "")[1:]:
        m = re.match(r"a/(\S+) b/", b)
        if not m:
            continue
        neuf = bool(re.search(r"(?m)^new file mode", b))
        if not is_brouillon(m.group(1), neuf):
            keep.append("diff --git " + b)
    return "".join(keep)


def container_up(s: dict, pull: bool = True) -> str:
    """Un conteneur NEUF par tour.

    Sans cela, les artefacts non suivis laissés par l'exécution précédente
    (caches `.dvc`, répertoires temporaires) survivent au `git checkout` et
    changent le résultat du tour suivant : mesuré sur `iterative__dvc-1262`, où
    DEUX TOURS AU PATCH BYTE-IDENTIQUE donnaient l'un vert, l'autre rouge.
    L'image étant déjà locale, `docker run` coûte quelques secondes.
    """
    n = cname(s["instance_id"])
    img = s["docker_image"]
    if pull:
        tire(img)
    sh(f"docker rm -f {n} >/dev/null 2>&1; "
       f"docker run -d --name {n} {img} sleep infinity >/dev/null", t=1800)
    if n not in sh(f"docker ps --format '{{{{.Names}}}}'", t=120):
        raise SystemExit(f"ÉCHEC : conteneur {n} absent")
    return n


def tire(img: str, essais: int = 12) -> None:
    """Tire l'image, en tenant compte du QUOTA DOCKER HUB.

    Le quota anonyme est de 100 pulls par heure et par IP (verifie sur l'hote :
    `ratelimit-limit: 100;w=3600`). Le rejeu en demande 154. Le `docker pull -q
    ... >/dev/null 2>&1` d'origine avalait l'echec : `docker run` echouait
    ensuite sur une image absente, et 87 instances — dont la TOTALITE de
    sqlglot — sont sorties du corpus sans que rien ne le dise.

    On ne tire pas ce qui est deja la, on attend le renouvellement de la
    fenetre plutot que d'abandonner, et un echec final est BRUYANT.
    """
    if sh(f"docker images -q {img}", t=120).strip():
        return
    dernier = ""
    for i in range(essais):
        dernier = sh(f"docker pull -q {img} 2>&1 | tail -2", t=3600)
        if sh(f"docker images -q {img}", t=120).strip():
            return
        print(f"  pull refuse ({i + 1}/{essais}) : {dernier.strip()[:120]}")
        time.sleep(400)
    raise SystemExit(f"ÉCHEC : image {img} intirable apres {essais} essais — {dernier[:200]}")


def reset_and_apply(n: str, s: dict, mp: str | None) -> dict:
    sh(f"docker exec {n} bash -lc 'cd /testbed && git checkout -f {s['base_commit']} 2>&1 "
       f"| tail -1 && git reset -q'", t=600)
    out = {"test_patch": "", "patch": "", "applied": True}
    tp = s["test_patch"] or ""
    if tp.strip():
        b = base64.b64encode(tp.encode()).decode()
        out["test_patch"] = sh(
            f"docker exec {n} bash -lc 'echo {b} | base64 -d > /tmp/tp.diff && "
            f"cd /testbed && git apply -v /tmp/tp.diff 2>&1 | tail -2'", t=300).strip()[-200:]
    if mp is not None:
        if not mp.strip():
            out["applied"] = False
            out["patch"] = "patch vide après retrait des brouillons"
            return out
        # Un diff unifié DOIT finir par un saut de ligne : sans lui `git apply`
        # échoue. 55,8 % des model_patch amont n'en ont pas, et le repli
        # `patch -p1` ne rattrapait rien — le tour ressortait « appliqué » et
        # ROUGE. Même piège qu'en P9b, en miroir.
        if not mp.endswith("\n"):
            mp += "\n"
        b = base64.b64encode(mp.encode()).decode()
        r = sh(f"docker exec {n} bash -lc 'echo {b} | base64 -d > /tmp/p.diff && cd /testbed && "
               f"(git apply -v /tmp/p.diff 2>&1 | tail -3 && echo P12_OK) || "
               f"(patch -p1 --fuzz=3 -i /tmp/p.diff 2>&1 | tail -3 && echo P12_FUZZ)'", t=600)
        out["patch"] = r.strip()[-300:]
        applique = ("P12_OK" in r) or ("P12_FUZZ" in r and "FAILED" not in r.upper())
        # CONTRÔLE POSITIF : ne pas croire le code de retour. Si l'arbre porte
        # vraiment le patch, alors le patch INVERSE s'y applique. Le test porte
        # sur le CONTENU, pas sur le texte du diff : `git diff` recanonicalise
        # les bornes de hunks et le contexte, si bien qu'une égalité de texte
        # rejetait 104 tours pourtant correctement appliqués.
        rev = sh(f"docker exec {n} bash -lc 'cd /testbed && "
                 f"git apply -R --check /tmp/p.diff && echo P12_REV_OK'", t=300)
        out["conforme"] = "P12_REV_OK" in rev
        out["applied"] = applique and out["conforme"]
        if not out["conforme"]:
            out["patch"] = (out["patch"] + " | ÉTAT NON CONFORME AU PATCH")[-300:]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "down"))
    ap.add_argument("iid")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    s = load(a.iid)
    n = cname(a.iid)
    if a.cmd == "down":
        sh(f"docker rm -f {n} >/dev/null 2>&1", t=300)
        print("supprimé", n)
        return 0

    n = container_up(s)
    rec: dict = {"instance_id": a.iid, "repo": s["repo"],
                 "n_declared": len(s["FAIL_TO_PASS"]),
                 "n_trajectories": len(s["trajectories"])}

    # étape 10 : double passe au parent, chacune dans un conteneur neuf
    reset_and_apply(n, s, None)
    p1 = run_tests(n, s)
    n = container_up(s, pull=False)
    reset_and_apply(n, s, None)
    p2 = run_tests(n, s)
    instables = sorted(set(p1["failed"]) ^ set(p2["failed"]))
    rec["parent_parsed"] = p1["parsed"] and p2["parsed"]
    rec["instables"] = instables
    rec["parent_failed"] = p1["failed"]
    if instables or not rec["parent_parsed"]:
        rec["ecartee"] = "instabilité au parent" if instables else "parent non analysé"
        (OUT / f"{a.iid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        print("ÉCARTÉE :", rec["ecartee"], instables[:5])
        sh(f"docker rm -f {n} >/dev/null 2>&1", t=300)
        return 1

    trajs = []
    for ti, bloc in enumerate(s["trajectories"]):
        tours = []
        for t in bloc:
            mp = code_patch(t["model_patch"])
            n = container_up(s, pull=False)
            ap_ = reset_and_apply(n, s, mp)
            if not ap_["applied"]:
                tours.append({"turn": t["turn"], "trajectory_id": t["trajectory_id"],
                              "applied": False, "motif": ap_["patch"][:200]})
                print(f"  traj {ti} tour {t['turn']}: PATCH NON APPLIQUÉ")
                continue
            tr = run_tests(n, s)
            manquants = sorted(set(s["FAIL_TO_PASS"]) - set(tr["observed"]))
            tours.append({"turn": t["turn"], "trajectory_id": t["trajectory_id"],
                          "applied": True, "parsed": tr["parsed"],
                          "resolved_upstream": t["resolved"],
                          "declares_non_observes": manquants,
                          # journal de `ordre_et_repare` : identifiants
                          # tronqués par l'amont résolus ou écartés, et
                          # identifiants absents de la collecte. Un test
                          # écarté sort du critère « aucun P2P cassé » : ça
                          # doit se voir.
                          "ids_repares": tr.get("ids_repares") or {},
                          "ids_ecartes": tr.get("ids_ecartes") or [],
                          "ids_hors_collecte": tr.get("ids_hors_collecte") or [],
                          "collecte_vide": bool(tr.get("collecte_vide")),
                          "failed_all": tr["failed"], "n_passed": len(tr["passed"]),
                          "diff": mp[:8000], "diff_chars": len(mp)})
            f2p = set(s["FAIL_TO_PASS"])
            print(f"  traj {ti} tour {t['turn']}: {len(f2p & set(tr['failed']))}/{len(f2p)} "
                  f"déclarés rouges, {len(tr['passed'])} verts"
                  + (f" | NON OBSERVÉS {len(manquants)}" if manquants else ""))
        trajs.append(tours)
    rec["trajectories"] = trajs
    (OUT / f"{a.iid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    sh(f"docker rm -f {n} >/dev/null 2>&1", t=300)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
