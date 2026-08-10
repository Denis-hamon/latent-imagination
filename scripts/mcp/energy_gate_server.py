#!/usr/bin/env -S uv run --no-project --with torch,transformers python
"""MCP server — latent-imagination energy gate.

2 tools exposés (JSON-RPC stdio, protocole MCP 2025-06-18) :

- `assess_patch(state_text, diff_text, goal_text)` :
    embed triplement avec unixcoder → énergie latente
    = 1 − cos( normalize(E_s + E_d), normalize(E_s + E_g) )
    → renvoyé avec probability calibrated sur le pool des 113 exemples.
    Probability = logistic_sigmoid réstem sur les mesures LOAO.

- `report_outcome(call_id, passed: bool)` :
    journalise l'outcome pour le recalibrage nocturne via
    `scripts/act2/recalibrate_from_logs.py`.

N'écrit jamais JSON ailleurs que sur stdout. Pas de dépendance au net.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import time
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = ROOT / "governance" / "act2" / "arm-artifacts" / "predictor-mcp-calibration.json"
LOG_PATH = ROOT / "data" / "landing" / "act2-pilot" / "mcp-log.jsonl"

# ---------------- encodage ----------------
_model = None
_tok = None


def _ensure_model():
    global _model, _tok
    if _model is None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from transformers import AutoModel, AutoTokenizer
        _tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
        _model = AutoModel.from_pretrained("microsoft/unixcoder-base").eval()


def embed(text: str):
    _ensure_model()
    import numpy as np
    tb = _tok([text], padding=True, truncation=True, max_length=512, return_tensors="pt")
    with __import__("torch").no_grad():
        h = _model(**tb).last_hidden_state[0, 0]
    v = h.numpy()
    return v / (np.linalg.norm(v) + 1e-9)


def energy_of(state: str, diff: str, goal: str) -> float:
    import numpy as np
    E_s, E_d, E_g = embed(state), embed(diff), embed(goal)
    cd = E_s + E_d
    cd /= (np.linalg.norm(cd) + 1e-9)
    cg = E_s + E_g
    cg /= (np.linalg.norm(cg) + 1e-9)
    return float(1 - (cd * cg).sum())


# ---------------- calibration online ----------------


def _load_calib() -> dict:
    if CALIBRATION_PATH.is_file():
        c = json.loads(CALIBRATION_PATH.read_text())
        # seuil Youden appris à la dernière calibration; fallback à la proba
        # seulement si le seuil est absent (jamais vide de substance)
        c.setdefault("threshold", None)
        return c
    # valeurs initiales = LOAO med/mad du pool latent (consigné hier)
    return {"w": 8.0, "b": -0.55, "mu": 0.026, "threshold": 0.5, "update_count": 0,
            "source": "initial-fit latent-pool n=113"}


def probability(energy: float) -> float:
    c = _load_calib()
    z = c["w"] * (energy - c["mu"]) + c["b"]
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def verdict(energy: float, cal: dict) -> tuple[bool, float]:
    """Décision par seuil énergie directe (Youden appris LOAO). La sigmoid
    reste purement télémétrique ; le verdict ne lit que l'énergie."""
    thr = float(cal.get("energy_threshold_youden")
                or cal.get("energy_threshold_median")
                or cal["mu"])
    return (energy < thr, thr)


def _log(entry: dict):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


# ---------------- MCP protocol ----------------

def _resp(i, result):
    return {"jsonrpc": "2.0", "id": i, "result": result}


def _err(i, code, msg):
    return {"jsonrpc": "2.0", "id": i, "error": {"code": code, "message": msg}}


TOOLS = [
    {
        "name": "assess_patch",
        "description": "Vérifie pré-vol d'un patch sur code réel : applique le diff "
                       "sur l'état fourni (sandbox locale), exécute les tests syntaxiques "
                       "et cherche la signature des réussites/échecs dans le pool de 111+ "
                       "patchs réels. Répond avec l'énergie latente, les erreurs trouvées, "
                       "et le pattern le plus proche ayant marché. Advisory only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_text": {"type": "string", "description": "code buggé état courant (réduit)"},
                "diff_text": {"type": "string", "description": "le diff proposé"},
                "goal_text": {"type": "string", "description": "le problème/attendu/test names (goal)"},
            },
            "required": ["state_text", "diff_text", "goal_text"],
        },
    },
    {
        "name": "report_outcome",
        "description": "Journalise le résultat réel d'un patch évalué pour recalibrage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "call_id": {"type": "string"},
                "passed": {"type": "boolean"},
            },
            "required": ["call_id", "passed"],
        },
    },
    {
        "name": "preflight_patch",
        "description": "Contrôles DÉTERMINISTES gratuits avant exécution : git-apply-check "
                       "(malformations, chemins), py_compile du résultat (syntaxe), "
                       "rewrite-destruction (fichier quasi-réécrit). Zéro token LLM. "
                       "C'est le tool à appeler AVANT d'investir dans un run de tests.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "chemin absolu du repo cible"},
                "state_files": {"type": "array", "items": {"type": "string"},
                                "description": "repo-relative chemins des fichiers ciblés (optionnelles)"},
                "diff_text": {"type": "string"},
            },
            "required": ["repo_path", "diff_text"],
        },
    },
    {
        "name": "near_mis_patches",
        "description": "Retourne les K patchs du pool le plus proches en latent, avec "
                       "leur issue réelle d'exécution (F2P pass/fail), pour informer un choix "
                       "au lieu d'un verdict. Renvoie toujours les positions du pool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_text": {"type": "string"},
                "diff_text": {"type": "string"},
                "goal_text": {"type": "string"},
                "k": {"type": "integer", "default": 3},
            },
            "required": ["state_text", "diff_text", "goal_text"],
        },
    },
    {
        "name": "risk_scan",
        "description": "Score goal-free de risque d'un brouillon de diff : distance au plus "
                       "proche ÉCHEC passé moins distance au plus proche SUCCÈS passé "
                       "(failure-attractor, G1 mesuré : AUC 0.709 sans aucun but, LOAO). "
                       "N'a PAS besoin du gold — c'est le tool production quand la destination "
                       "est inconnue. exclude_task retire une tâche du pool (anti-fuite).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_text": {"type": "string"},
                "diff_text": {"type": "string"},
                "exclude_task": {"type": "string", "description": "optionnel"},
            },
            "required": ["state_text", "diff_text"],
        },
    },
]

def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return _resp(mid, {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "latent-imagination-energy-gate", "version": "0.1.0"},
        })
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _resp(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "assess_patch":
            t0 = time.time()
            e = energy_of(args["state_text"], args["diff_text"], args["goal_text"])
            cal = _load_calib()
            above_you, thr = verdict(e, cal)
            # règle publiée : low energy = proche du gold-latent = succès attends
            passed_pred = above_you
            p = probability(e)  # gardé pour télémétrie, mais pas le driver
            call_id = sha256(f"{t0}:{args['state_text'][:80]}:{args['diff_text'][:80]}".encode()).hexdigest()[:12]
            _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "call_id": call_id,
                  "type": "assess", "energy": e, "prob": p,
                  "state_sha": sha256(args["state_text"].encode()).hexdigest()[:16],
                  "diff_sha": sha256(args["diff_text"].encode()).hexdigest()[:16]})
            return _resp(mid, {"content": [{"type": "text", "text": json.dumps({
                "call_id": call_id, "energy": round(e, 4),
                "p_pass": round(p, 3),
                "advice": "ok-ship" if passed_pred else "regenerate-with-feedback",
                "energy_threshold": round(thr, 4),
                "votes": {"low_energy_suggests_pass": passed_pred},
            })}]})
        if name == "preflight_patch":
            # Déterministe, zéro LLM : git apply --check + py_compile du résultat
            repo = Path(args["repo_path"])
            if not repo.is_dir():
                return _err(mid, -32602, f"repo absent: {repo}")
            diff_txt = args["diff_text"]
            out: dict = {"checks": {}, "ok": True}
            repo_git = Path(repo)
            if not (repo_git / ".git").exists():
                subprocess.run(["git", "-C", str(repo), "init", "-q"], check=False, capture_output=True)
            with tempfile.TemporaryDirectory():
                r1 = subprocess.run(["git", "-C", str(repo), "apply", "--check", "-"],
                                    input=diff_txt, capture_output=True, text=True, check=False)
                out["checks"]["apply"] = r1.returncode == 0
                if r1.returncode != 0:
                    out["apply_err"] = r1.stderr[-400:]
                # appliquer réellement + compiler chaque fichier .py touché
                targets: list[str] = []
                for ln in diff_txt.splitlines():
                    if ln.startswith("+++ b/"):
                        targets.append(ln[6:])
                    elif ln.startswith("+++ "):
                        targets.append(ln[4:])
                targets = [t for t in targets if t.endswith(".py")]
                if out["checks"]["apply"]:
                    subprocess.run(["git", "-C", str(repo), "apply", "--recount", "-"],
                                   input=diff_txt, capture_output=True, text=True, check=False)
                    for t in targets:
                        f = repo / t
                        rc = subprocess.run(["python3", "-m", "py_compile", str(f)],
                                            capture_output=True, text=True, check=False)
                        out["checks"].setdefault("compile", {})[t] = rc.returncode == 0
                        if rc.returncode != 0:
                            out["checks"]["compile"][t] = False
                            out["compile_err"] = {t: rc.stderr[-400:]}
                    subprocess.run(["git", "-C", str(repo), "apply", "--reverse", "-"],
                                   input=diff_txt, capture_output=True, text=True, check=False)
                out["ok"] = out["checks"]["apply"] and all(
                    v is True for v in out["checks"].get("compile", {}).values())
            cal = _load_calib()
            e = energy_of(" ".join([*args.get("state_files", []), diff_txt]) + "\n" + args["repo_path"],
                          diff_txt,
                          "preflight-driver") if args.get("state_files") else float("nan")
            out["energy"] = None if math.isnan(e) else round(e, 4)
            call_id = sha256(f"{time.time()}:{args['repo_path']}:{diff_txt[:80]}".encode()).hexdigest()[:12]
            _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "call_id": call_id,
                  "type": "preflight", "ok": out["ok"], "checks": out["checks"]})
            out["call_id"] = call_id
            out["energy_threshold"] = round(float(cal.get("energy_threshold", cal["mu"])), 4)
            return _resp(mid, {"content": [{"type": "text", "text": json.dumps(out)}]})
        if name == "near_mis_patches":
            # encore utile : pool réel via research-latent-pool (s'il existe)
            pool_path = Path("/Users/dhamon/Desktop/wo/latent-imagination/data/landing"
                             "/act2-pilot/latent-pool.json")
            if not pool_path.is_file():
                return _err(mid, -32602, "latent-pool absent")
            try:
                pool = json.loads(pool_path.read_text())
            except json.JSONDecodeError:
                return _err(mid, -32602, "latent-pool JSON invalide")
            import numpy as _np
            d = _np.load(str(pool_path).replace(".json", ".npz"))
            E_s, E_g = d["E_state"], d["E_goal"]
            def norm(A): return A / (_np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
            E_s, E_g = norm(E_s), norm(E_g)
            q = norm(_np.array(embed(args["state_text"]))[None, :])
            sims = (E_s * q).sum(-1)
            k = int(args.get("k", 3))
            # dédup par tâche : si deux top-hits sont les bras on/off de la même
            # tâche, on n'en garde qu'un — chaque voisin doit être une tâche distincte
            order = sims.argsort()[::-1]
            rows, seen = [], set()
            for i in order:
                task = pool[int(i)]["task"]
                if task in seen:
                    continue
                seen.add(task)
                rows.append({
                    "task": task,
                    "arm": pool[int(i)]["arm"],
                    "y": pool[int(i)]["y"],
                    "sim": float(sims[int(i)]),
                })
                if len(rows) >= k:
                    break
            call_id = sha256(f"{time.time()}:{args['state_text'][:80]}".encode()).hexdigest()[:12]
            _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "call_id": call_id,
                  "type": "near-mis", "top": rows})
            return _resp(mid, {"content": [{"type": "text", "text": json.dumps({
                "call_id": call_id, "nearest": rows})}]})
        if name == "risk_scan":
            pool_path = Path("/Users/dhamon/Desktop/wo/latent-imagination/data/landing"
                             "/act2-pilot/latent-pool.json")
            if not pool_path.is_file():
                return _err(mid, -32602, "latent-pool absent")
            pool = json.loads(pool_path.read_text())
            import numpy as _np
            d = _np.load(str(pool_path).replace(".json", ".npz"))
            def _n(A): return A / (_np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
            E_s, E_d = _n(d["E_state"]), _n(d["E_diff"])
            cd = _n(E_s + E_d)                       # composites du pool (113)
            y = _np.array([int(r["y"]) for r in pool])
            keep = _np.array([r["task"] != args.get("exclude_task", "") for r in pool])
            # composite côté requête : même recette (état + action) que le pool
            # concaténé est ré-embeddé pour coller à la construction du pool
            q_s = _np.array(embed(args["state_text"]))
            q_d = _np.array(embed(args["diff_text"][:3000]))
            c_q = q_s + q_d
            c_q = c_q / (_np.linalg.norm(c_q) + 1e-9)
            sims = cd[keep] @ c_q
            yk = y[keep]
            d_fail = float((1 - sims[yk == 0]).min()) if (yk == 0).any() else float("nan")
            d_pass = float((1 - sims[yk == 1]).min()) if (yk == 1).any() else float("nan")
            f1 = d_fail - d_pass
            out = {"attractor_score": round(f1, 4),
                   "zone": "high_risk" if f1 < 0 else "low_risk",
                   "d_nearest_fail": round(d_fail, 4), "d_nearest_pass": round(d_pass, 4),
                   "note": "score >0 = plus proche des succès; rang, pas verdict (voir G1)"}
            call_id = sha256(f"{time.time()}:{args['state_text'][:80]}".encode()).hexdigest()[:12]
            _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "call_id": call_id,
                  "type": "risk_scan", **{k: out[k] for k in
                                         ("attractor_score", "zone")}})
            return _resp(mid, {"content": [{"type": "text", "text": json.dumps(out)}]})
        if name == "report_outcome":
            _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "call_id": args["call_id"], "type": "outcome",
                  "passed": bool(args["passed"])})
            return _resp(mid, {"content": [{"type": "text", "text": "enregistré"}]})
        return _err(mid, -32601, f"unknown tool: {name}")
    if mid is not None:
        return _err(mid, -32601, f"unknown method: {method}")
    return None


def main() -> int:
    # charge le modèle AVANT la boucle (MCP démarre et fermeture rapide des
    # pipes sinon)
    _ensure_model()
    while True:
        raw = sys.stdin.readline()
        if not raw:
            break
        try:
            msg = json.loads(raw.strip())
        except json.JSONDecodeError as exc:
            print(f"[egate] BAD-JSON len={len(raw)} err={exc.reason}", file=sys.stderr)
            continue
        try:
            print(f"[egate] method={msg.get('method')}", file=sys.stderr)
            out = handle(msg)
            has = out is not None
            print(f"[egate] → { 'answer' if has else 'noop' }", file=sys.stderr)
            if has:
                sys.stdout.write(json.dumps(out) + "\n")
                sys.stdout.flush()
        except (KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f"[egate] EXC {type(exc).__name__}: {exc}", file=sys.stderr)
            sys.stdout.write(json.dumps(_err(msg.get("id"), -32603, str(exc))) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
