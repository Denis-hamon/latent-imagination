"""P9 étapes 6 à 11 — rejeu des trajectoires importées, vérité par exécution.

  reconstruct <id>   rejoue les actions d'édition, capture l'état cumulé après
                     chacune, et confronte l'état final à `model_patch` (D5).
  execute <id>       rejoue jusqu'à 5 états échantillonnés, exécute les tests
                     déclarés à chacun, plus la double passe au parent (D10).
  run <id>           les deux.

ZÉRO appel LLM. Aucune trajectoire n'est réparée à la main : une reconstruction
qui diverge est écartée et COMPTÉE.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / "py-p9"
OUT = D / "p9-replay"
# HOST = la machine ou tournent les conteneurs. Le rejeu a toujours ete pilote
# DEPUIS LE MAC, `sh` passant par ssh. Cette topologie a coute 58 instances dans
# la nuit du 29 au 30/08 : le Mac s'est endormi (« Clamshell Sleep ») et le
# transport a disparu au milieu de la campagne.
#
# `LI_HOST=local` fait tourner l'orchestrateur SUR le serveur, ou `sh` execute
# en local au lieu de traverser un ssh qui n'existe pas la-bas. Le Mac sort
# alors completement de la boucle, et son couvercle avec.
HOST = os.environ.get("LI_HOST", "Kimsufi-standard")
CONDA = ("source /opt/conda/etc/profile.d/conda.sh && conda activate testbed && "
         "export PYTHONPATH=/testbed/src:/testbed:$PYTHONPATH")
MAX_STATES = 5


def sh(cmd: str, t: int = 900) -> str:
    argv = (["bash", "-lc", cmd] if HOST == "local"
            else ["ssh", "-o", "ConnectTimeout=15", HOST, cmd])
    r = subprocess.run(argv, capture_output=True, timeout=t)
    return (r.stdout + r.stderr).decode("utf-8", "replace")


def load(iid: str) -> tuple[dict, dict, dict]:
    sel = {x["instance_id"]: x for x in json.loads((D / "p9-selection.json").read_text())}
    # `p9-context.json` ne couvre que les 45 irréductibles (fenêtre P9b) ;
    # le rejeu P9 porte sur les 120 de la sélection gelée.
    ctx = json.loads((D / "p9-context-120.json").read_text())
    traj = None
    for line in (D / "p9-trajectories.jsonl").read_text().splitlines():
        if line.strip() and json.loads(line)["instance_id"] == iid:
            traj = json.loads(line)
            break
    if traj is None:
        raise SystemExit(f"pas de trajectoire pour {iid}")
    return sel[iid], ctx[iid], traj


def image_of(t: dict) -> str:
    img = t.get("docker_image")
    if img:
        return img
    org, rest = t["instance_id"].split("__", 1)
    return "swerebench/sweb.eval.x86_64.{}_1776_{}".format(org, rest).lower()


def cname(iid: str) -> str:
    return "p9r-" + re.sub(r"[^a-zA-Z0-9_.-]", "-", iid)


def is_brouillon(path: str, neuf: bool) -> bool:
    """Un fichier hors périmètre de code : carnet de bord d'agent, ou script
    jetable créé à la racine (`reproduce_issue.py`, `test_edge_cases.py`…).

    `neuf` distingue le brouillon du vrai fichier racine : `setup.py` existe au
    commit de base, `reproduce_issue.py` non.
    """
    return path.startswith(".openhands/") or ("/" not in path and neuf)


def patch_files(mp: str) -> dict[str, bool]:
    """{chemin: est_neuf} pour chaque fichier d'un diff unifié."""
    out = {}
    for b in re.split(r"(?m)^diff --git ", mp or "")[1:]:
        m = re.match(r"a/(\S+) b/", b)
        if m:
            out[m.group(1)] = bool(re.search(r"(?m)^new file mode", b))
    return out


def restrict_diff(text: str, paths: set[str]) -> str:
    """Ne garder que les blocs de fichiers du périmètre."""
    keep = []
    for b in re.split(r"(?m)^diff --git ", text or "")[1:]:
        m = re.match(r"a/(\S+) b/", b)
        if m and m.group(1) in paths:
            keep.append("diff --git " + b)
    return "".join(keep)


def edit_scope(traj: dict) -> set[str]:
    """Les chemins de CODE que l'éditeur de l'agent a touchés.

    C'est le périmètre de la reconstruction : ce que le rejeu prétend
    reproduire. Tout ce que `model_patch` contient en dehors est compté
    (`hors_perimetre`) et rend l'instance divergente — jamais rattrapé.
    """
    scope = {}
    for a in edit_actions(traj):
        m = re.match(r"^/workspace/[^/]+/(.*)$", a.get("path") or "")
        if not m:
            continue
        p = m.group(1)
        scope[p] = scope.get(p, False) or (a.get("command") == "create")
    return {p for p, neuf in scope.items() if not is_brouillon(p, neuf)}


def edit_actions(traj: dict) -> list[dict]:
    """Les seules actions qui modifient un fichier : `create` et `str_replace`.

    Mesuré sur les 120 trajectoires : ni `insert` ni `undo_edit` n'apparaît.
    `task_tracker` (`.openhands/TASKS.md`) et `execute_bash` ne sont PAS rejoués ;
    l'écart que cela crée est mesuré, pas masqué — voir `edit_scope`.
    """
    acts = []
    for c in traj["calls"]:
        if c["name"] != "str_replace_editor":
            continue
        try:
            a = json.loads(c["arguments"])
        except Exception:
            acts.append({"command": "<json-invalide>"})
            continue
        if a.get("command") in ("create", "str_replace"):
            acts.append(a)
    return acts


def test_paths(test_patch: str) -> list[str]:
    return sorted({m for m in re.findall(r"^diff --git a/(\S+) b/", test_patch or "",
                                         re.MULTILINE)})


def normalize_diff(text: str) -> str:
    """Normalisation autorisée par l'étape 7 : en-têtes `index`, espaces de fin,
    ordre des fichiers. Rien d'autre — aucun chemin n'est écarté ici."""
    blocks, cur = [], []
    for line in (text or "").splitlines():
        if line.startswith("diff --git "):
            if cur:
                blocks.append(cur)
            cur = [line]
        elif cur is not None and cur:
            cur.append(line)
    if cur:
        blocks.append(cur)
    norm = []
    for b in blocks:
        keep = [l.rstrip() for l in b
                if not l.startswith("index ") and not l.startswith("new file mode")
                and not l.startswith("deleted file mode") and not l.startswith("old mode")
                and not l.startswith("new mode")]
        norm.append("\n".join(keep).rstrip())
    return "\n".join(sorted(norm))


# --- script embarqué dans le conteneur : applique les actions, rend les diffs
APPLIER = r'''
import json, os, re, subprocess, sys

acts = json.load(open("/tmp/acts.json"))
upto = int(sys.argv[1]) if len(sys.argv) > 1 else len(acts)
excl = json.load(open("/tmp/excl.json")) if os.path.exists("/tmp/excl.json") else []

def to_testbed(p):
    # /workspace/<org>__<repo>__<ver>/reste -> /testbed/reste
    m = re.match(r"^/workspace/[^/]+/(.*)$", p or "")
    if m:
        return "/testbed/" + m.group(1)
    if (p or "").startswith("/testbed/"):
        return p
    return None

def gitdiff():
    # `-N` fait apparaitre les fichiers neufs ; le perimetre `excl` (ici la
    # liste des chemins de code edites par l'agent) borne ce qui est capture.
    subprocess.run(["git", "add", "-A", "-N"], cwd="/testbed",
                   capture_output=True)
    cmd = ["git", "diff", "--"] + (excl if excl else ["."])
    r = subprocess.run(cmd, cwd="/testbed", capture_output=True)
    return r.stdout.decode("utf-8", "replace")

states, fails = [], []
for i, a in enumerate(acts[:upto]):
    p = to_testbed(a.get("path"))
    try:
        if p is None:
            raise ValueError("chemin hors workspace: %r" % a.get("path"))
        if a["command"] == "create":
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(a.get("file_text") or "")
        else:
            s = open(p).read()
            old = a.get("old_str") or ""
            n = s.count(old)
            if n == 0:
                raise ValueError("old_str absent")
            if n > 1:
                raise ValueError("old_str ambigu (%d)" % n)
            open(p, "w").write(s.replace(old, a.get("new_str") or "", 1))
    except Exception as e:
        fails.append({"i": i, "cmd": a.get("command"), "err": str(e)[:120]})
    states.append(gitdiff())

print("<<<P9JSON>>>" + json.dumps({"states": states, "fails": fails}))
'''


def container_up(iid: str) -> tuple[dict, dict, dict, str]:
    tk, tc, traj = load(iid)
    n = cname(iid)
    sh(f"docker pull -q {image_of(tk)} >/dev/null 2>&1", t=3600)
    sh(f"docker rm -f {n} >/dev/null 2>&1; "
       f"docker run -d --name {n} {image_of(tk)} sleep infinity >/dev/null", t=1800)
    if n not in sh(f"docker ps --format '{{{{.Names}}}}'", t=120):
        raise SystemExit(f"ÉCHEC : conteneur {n} absent")
    b64 = base64.b64encode(APPLIER.encode()).decode()
    sh(f"docker exec {n} bash -lc 'echo {b64} | base64 -d > /tmp/applier.py'", t=120)
    return tk, tc, traj, n


def reset_repo(n: str, base: str, test_patch: str | None,
               scope: list[str] | None = None) -> str:
    """Remet le dépôt au parent.

    Le nettoyage est BORNÉ aux chemins du périmètre : un `git clean` global
    détruit les extensions C préconstruites des images (mesuré en P9b sur
    Pillow, où plus aucun module PIL n'était importable). Sans nettoyage du
    tout, un fichier neuf créé par un état précédent survivrait au rejeu de
    l'état suivant et polluerait son diff.
    """
    paths = " ".join(f"'{x}'" for x in (scope or []))
    clean = f" && git clean -fdq -- {paths}" if paths else ""
    sh(f"docker exec {n} bash -lc 'cd /testbed && git checkout -f {base} 2>&1 | tail -1 "
       f"&& git reset -q{clean} 2>/dev/null; true'", t=600)
    if test_patch and test_patch.strip():
        b = base64.b64encode(test_patch.encode()).decode()
        return sh(f"docker exec {n} bash -lc 'echo {b} | base64 -d > /tmp/tp.diff && "
                  f"cd /testbed && git apply -v /tmp/tp.diff 2>&1 | tail -2'", t=300)
    return "sans test_patch"


def apply_actions(n: str, acts: list[dict], upto: int, excl: list[str]) -> dict:
    a64 = base64.b64encode(json.dumps(acts).encode()).decode()
    e64 = base64.b64encode(json.dumps(excl).encode()).decode()
    raw = sh(f"docker exec {n} bash -lc 'echo {a64} | base64 -d > /tmp/acts.json && "
             f"echo {e64} | base64 -d > /tmp/excl.json && "
             f"python /tmp/applier.py {upto}'", t=900)
    m = raw.find("<<<P9JSON>>>")
    if m < 0:
        return {"error": raw[-500:]}
    return json.loads(raw[m + len("<<<P9JSON>>>"):])


def ordre_et_repare(n: str, tests: list[str]) -> tuple[list[str], dict]:
    """Met les tests dans l'ORDRE DE COLLECTE de pytest et répare les
    identifiants tronqués par le dataset amont. Une seule passe
    `--collect-only` sert aux deux.

    ORDRE. `run_tests` passait FAIL_TO_PASS d'abord, puis PASS_TO_PASS. pytest
    exécute les identifiants nommés DANS L'ORDRE DONNÉ : le test déclaré
    partait donc d'un interpréteur froid. Pillow-6917 en est le cas témoin —
    `test_register_open_duplicates` lit `Image.OPEN["JPEG"]`, qui n'existe
    qu'une fois les plugins initialisés par un test antérieur. En tête, il
    lève `KeyError: 'JPEG'` ; à sa place de collecte, la campagne rend
    « 108 passed ». Cet ordre d'arguments FABRIQUAIT des rouges : il gonfle
    y=1 et diminue persist=0. L'ordre de collecte retrouve le verdict amont,
    c'est le controle positif de la regle.

    IDENTIFIANTS. Les champs amont ont ete construits en decoupant sur les
    espaces : un test parametre dont le parametre en contient ressort coupe —
    `test_image_modes_fail[very` pour `...[very very long]`. pytest refuse
    l'argument et ANNULE TOUTE la campagne. On resout par prefixe sur les
    identifiants reellement collectes ; ambigu ou introuvable, l'identifiant
    est ecarte et journalise.

    Si la collecte echoue, on NE se rabat PAS en silence : le journal porte
    `collecte_vide` et l'ordre d'origine est conserve.
    """
    fichiers = sorted({t.split("::")[0] for t in tests})
    raw = sh(f"docker exec {n} bash -lc '{CONDA} && cd /testbed && "
             f"pytest --collect-only -q -p no:cacheprovider {' '.join(fichiers)} "
             f"2>/dev/null'", t=1200)
    ordre = [l.strip() for l in raw.splitlines() if "::" in l]
    if not ordre:
        return tests, {"collecte_vide": True}
    rang = {r: i for i, r in enumerate(ordre)}
    repares, ecartes, out = {}, [], []
    for t in tests:
        if t.count("[") == t.count("]"):
            out.append(t)
            continue
        cands = [r for r in ordre if r.startswith(t)]
        if len(cands) == 1:
            repares[t] = cands[0]
            out.append(cands[0])
        else:
            ecartes.append({"id": t, "candidats": len(cands)})
    # un identifiant que la collecte ne connait pas est rejete en fin de liste :
    # on ne le perd pas, on ne le classe pas au hasard.
    inconnus = [t for t in out if t not in rang]
    # rangs de repli calcules AVANT le tri : `out.index` pendant un `sort` en
    # place lit une liste deja permutee et leve ValueError.
    repli = {t: len(ordre) + i for i, t in enumerate(out)}
    out.sort(key=lambda t: rang.get(t, repli[t]))
    return out, {"ids_repares": repares, "ids_ecartes": ecartes,
                 "ids_hors_collecte": inconnus}


def run_tests(n: str, tk: dict) -> dict:
    tests = list(tk["FAIL_TO_PASS"]) + list(tk["PASS_TO_PASS"])
    tests, journal = ordre_et_repare(n, tests)
    cmd = tk["test_cmd"] or "pytest --no-header -rA --tb=line --color=no -p no:cacheprovider"
    cmd += " --maxfail=0"
    b64 = base64.b64encode("\n".join(tests).encode()).decode()
    raw = sh(f"docker exec {n} bash -lc '{CONDA} && cd /testbed && "
             f"echo {b64} | base64 -d > /tmp/tests.txt && "
             f'xargs -d "\\n" -a /tmp/tests.txt {cmd}'
             f" 2>&1 | tail -400'", t=1800)
    failed, passed = set(), set()
    for line in raw.splitlines():
        m = re.match(r"^(PASSED|FAILED|ERROR)\s+(\S+)", line.strip())
        if m and ("::" in m.group(2) or m.group(2).endswith(".py")):
            (passed if m.group(1) == "PASSED" else failed).add(m.group(2))
    return {"failed": sorted(failed), "passed": sorted(passed),
            "observed": sorted(passed | failed), "parsed": bool(failed or passed),
            "raw_tail": raw[-1500:], **journal}


def sample_indexes(n_states: int) -> list[int]:
    """Au plus 5 états équirépartis en index, le dernier toujours inclus."""
    if n_states <= MAX_STATES:
        return list(range(n_states))
    step = (n_states - 1) / (MAX_STATES - 1)
    idx = sorted({round(i * step) for i in range(MAX_STATES)})
    idx[-1] = n_states - 1
    return sorted(set(idx))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("reconstruct", "execute", "run", "down"))
    ap.add_argument("iid")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    n = cname(a.iid)

    if a.cmd == "down":
        sh(f"docker rm -f {n} >/dev/null 2>&1", t=300)
        print("supprimé", n)
        return 0

    tk, tc, traj, n = container_up(a.iid)
    acts = edit_actions(traj)
    tpaths = set(test_paths(tc["test_patch"]))
    scope = edit_scope(traj)
    # ce que `model_patch` contient de code HORS du périmètre reconstruit :
    # créé par `execute_bash` (formateur, réparation d'environnement, effets de
    # bord d'exécution). Compté, jamais rattrapé.
    hors = sorted(p_ for p_, neuf in patch_files(traj["model_patch"]).items()
                  if not is_brouillon(p_, neuf) and p_ not in scope)
    rec: dict = {"instance_id": a.iid, "repo": tk["repo"],
                 "trajectory_id": traj["trajectory_id"], "resolved_upstream": traj["resolved"],
                 "n_edit_actions": len(acts), "scope": sorted(scope),
                 "hors_perimetre": hors}

    # --- étape 6 + 7 : reconstruction et contrôle d'intégrité D5
    print(reset_repo(n, tk["base_commit"], None, sorted(scope)).strip()[-120:])
    r = apply_actions(n, acts, len(acts), sorted(scope))
    if "error" in r:
        rec.update({"d5": False, "d5_motif": "applier: " + r["error"][:200]})
        (OUT / f"{a.iid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        print(json.dumps(rec, indent=1, ensure_ascii=False)[:800])
        return 1
    final = r["states"][-1] if r["states"] else ""
    attendu = restrict_diff(traj["model_patch"] or "", scope)
    d5_perimetre = normalize_diff(final) == normalize_diff(attendu)
    # D5 tel que scellé : égalité STRICTE de l'état final et de `model_patch`.
    d5_strict = normalize_diff(final) == normalize_diff(traj["model_patch"] or "")
    rec.update({"n_action_fails": len(r["fails"]), "action_fails": r["fails"][:5],
                "d5_strict": d5_strict, "d5_perimetre": d5_perimetre,
                "d5": d5_perimetre and not hors,
                "final_chars": len(final), "model_patch_chars": len(traj["model_patch"] or "")})
    print(f"D5 périmètre {'OK' if d5_perimetre else 'ÉCHEC'}"
          f" | strict {'OK' if d5_strict else 'ÉCHEC'}"
          f" | hors périmètre {len(hors)} | actions {len(acts)}"
          f" | échecs d'action {len(r['fails'])}")
    if a.cmd == "reconstruct":
        (OUT / f"{a.iid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        return 0

    # --- étape 10 : double passe au parent
    print(reset_repo(n, tk["base_commit"], tc["test_patch"], sorted(scope)).strip()[-120:])
    p1 = run_tests(n, tk)
    p2 = run_tests(n, tk)
    instables = sorted(set(p1["failed"]) ^ set(p2["failed"]))
    rec["parent_parsed"] = p1["parsed"] and p2["parsed"]
    rec["instables"] = instables
    if instables or not rec["parent_parsed"]:
        rec["ecartee"] = "instabilité au parent" if instables else "parent non analysé"
        (OUT / f"{a.iid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        print("ÉCARTÉE :", rec["ecartee"], instables[:5])
        return 1

    # --- étapes 8 + 9 : états échantillonnés, vérité par exécution
    idxs = sample_indexes(len(acts))
    rec["sampled"] = idxs
    tours = []
    for k in idxs:
        reset_repo(n, tk["base_commit"], tc["test_patch"], sorted(scope))
        rr = apply_actions(n, acts, k + 1, sorted(scope - tpaths))
        if "error" in rr:
            rec["ecartee"] = f"rejeu impossible à l'état {k}"
            break
        tr = run_tests(n, tk)
        manquants = sorted(set(tk["FAIL_TO_PASS"]) - set(tr["observed"]))
        tours.append({"state_index": k, "parsed": tr["parsed"],
                      "declares_non_observes": manquants,
                      "failed_all": tr["failed"], "n_passed": len(tr["passed"]),
                      "diff": rr["states"][-1] if rr["states"] else "",
                      "diff_chars": len(rr["states"][-1] if rr["states"] else "")})
        print(f"  état {k}: {len(tr['failed'])} en échec, {len(tr['passed'])} verts"
              + (f" | NON OBSERVÉS {manquants}" if manquants else ""))
    rec["tours"] = tours
    (OUT / f"{a.iid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    if not a.keep:
        sh(f"docker rm -f {n} >/dev/null 2>&1", t=300)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
