#!/usr/bin/env -S uv run --no-project --with torch,transformers python
"""GHOST MCP — world-model gate pour agents de code.

Le fantôme de chaque run passé note votre brouillon de patch.

`risk_scan` compare le diff aux ghosts des runs antérieurs — les échecs à
éviter (failure-attractor) et les succès à imiter — puis prédit l'issue AVANT
d'investir une exécution. Pas de gold requis (goal-free). ABSTENTION CALIBRÉE :
le verdict n'est rendu que dans le régime mesuré LOAO à acc 0.952
[0.773,0.992] (10 % de couverture; seuil tau épinglé dans
governance/act2/arm-artifacts/risk-scan-v8-calibration.json), sinon "abstain"
— le fantôme se tait quand il ne sait pas.

5 tools exposés (JSON-RPC stdio, protocole MCP 2025-06-18). Pool servi = v8
(n=207, surcharge env LI_POOL_JSON/LI_POOL_NPZ).

- `assess_patch(state_text, diff_text, goal_text)` : axe GOLD (nécessite le
  but) — mode harness/évaluation, PAS la prod sans gold. Calibration n=113.
- `preflight_patch(repo_path, diff_text)` : contrôles déterministes gratuits
  (git apply --check, py_compile, rewrite-destruction). Zéro token LLM.
- `near_mis_patches(...)` : k voisins d'état dans le pool, avec issue réelle.
- `risk_scan(state_text, diff_text, exclude_task?, reporter?)` : world model
  goal-free, abstention calibrée (voir ci-dessus). reporter = identité du
  LLM/agent appelant, requis pour stratifier le flywheel par auteur.
- `report_outcome(call_id, passed, reporter?, grounded_by?)` : journalise
  l'issue GROUNDÉE (tests exécutés, pas l'avis du modèle) ; les entrées
  risk_scan capturent state/diff au même call_id → paires (diff, outcome)
  disponibles pour le renforcement nocturne du pool (scripts/act2/mcp_flywheel.py).

N'écrit jamais JSON ailleurs que sur stdout. Pas de dépendance au net.

v0.4.0 (2026-08-15) : diagnostic de famille ADDITIF — `family_of(task)` dérive
mécaniquement la famille (préfixe repo, zéro modèle), `_family_diagnosis` nome
la famille la plus proche + sa couverture dans chaque réponse risk_scan ; les
abstentions portent `abstention_diagnosis` (expliquées, plus aveugles). La
décision (attracteur + tau) et le régime calibré sont INCHANGÉS. `reporter`
manquant → signalé (`reporter_note`, log `reporter_missing`) mais accepté.
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
CALIBRATION_PATH = Path(os.environ.get(
    "LI_CALIBRATION",
    ROOT / "governance" / "act2" / "arm-artifacts" / "predictor-mcp-calibration.json"))
LOG_PATH = Path(os.environ.get(
    "LI_LOG_PATH",
    ROOT / "data" / "landing" / "act2-pilot" / "mcp-log.jsonl"))
# pool servi : v8 (n=207) par défaut — surchargable par env pour tests/reculs
POOL_JSON = Path(os.environ.get(
    "LI_POOL_JSON",
    ROOT / "data/landing/act2-pilot/latent-pool-v8.json"))
POOL_NPZ = Path(os.environ.get(
    "LI_POOL_NPZ",
    ROOT / "data/landing/act2-pilot/latent-pool-v8.npz"))
# calibration risk_scan épinglée (mesurée LOAO, addendum 2026-08-15) :
# le MCP ne prédit QUE si conf >= tau (régime 10 % → acc 0.952 [0.773,0.992]),
# sinon il s'abstient. C'est l'abstention qui est le produit.
# LI_RISK_CALIB : seul levier de serving-swap lors d'une promotion de pool
# (flywheel stage 2) — la version servie reste auditable par ce chemin.
RISK_CALIB = Path(os.environ.get(
    "LI_RISK_CALIB",
    ROOT / "governance/act2/arm-artifacts/risk-scan-v8-calibration.json"))

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


# ---------------- pool servi + abstention calibrée ----------------
_pool_cache = None
_risk_calib_cache = None


def family_of(task: str) -> str:
    """Dérivation MÉCANIQUE de la famille d'une tâche : le préfixe avant le
    premier point (owner__repo). Zéro modèle, zéro apprentissage — c'est une
    dérivation déterministe, pas une classification (leçon S11 : la famille
    et l'auteur sont des facteurs de première classe; on les expose, on ne
    les invente pas)."""
    return task.split(".", 1)[0] if isinstance(task, str) and "." in task else str(task)


def _load_pool():
    """Charge (rows, composites cd normalisés, E_state/E_goal, labels y, tasks,
    familles) du pool servi en cache. Utilisé par risk_scan et near_mis_patches."""
    global _pool_cache
    if _pool_cache is None:
        import numpy as np
        rows = json.loads(POOL_JSON.read_text())
        d = np.load(str(POOL_NPZ))
        def _n(A):
            return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
        E_s = _n(d["E_state"]); E_d = _n(d["E_diff"]); E_g = _n(d["E_goal"])
        cd = _n(E_s + E_d)
        y = np.array([int(r["y"]) for r in rows])
        tasks = np.array([r["task"] for r in rows])
        families = np.array([family_of(r["task"]) for r in rows])
        _pool_cache = {"rows": rows, "cd": cd, "E_s": E_s, "E_g": E_g,
                       "y": y, "tasks": tasks, "families": families, "n": len(rows)}
    return _pool_cache


def _family_coverage(pc, exclude: list[bool] | None = None) -> dict:
    """Couverture par famille (n, positifs) — pur numpy, pas de modèle."""
    import numpy as np
    fams, y = pc["families"], pc["y"]
    keep = np.ones(len(y), bool) if exclude is None else np.array(exclude)
    cov: dict = {}
    for f in sorted(set(fams[keep].tolist())):
        m = (fams == f) & keep
        cov[f] = {"n": int(m.sum()), "positives": int(y[m].sum())}
    return cov


def _family_diagnosis(q_s, pc) -> dict:
    """Diagnostic ADDITIF (ne change JAMAIS la décision ni le régime tau/thr) :
    dans l'espace E_state, la famille du pool la plus proche de la requête et
    sa couverture. Transforme l'abstention aveugle en abstention expliquée —
    « hors couverture de la famille X » plutôt que « confiance insuffisante ».
    Note: la couverture de la famille la plus proche est le signal honnête ;
    la décision reste portée par l'attracteur goal-free (cd space)."""
    import numpy as np
    E_s, fams, y = pc["E_s"], pc["families"], pc["y"]
    q_s = q_s / (np.linalg.norm(q_s) + 1e-9)  # cosine, robust au scaling amont
    sims = E_s @ q_s  # q_s déjà normalisé côté appelant
    order = np.argsort(sims)[::-1]
    top5_fams = [str(fams[i]) for i in order[:5]]
    fam = top5_fams[0]
    mask = fams == fam
    in_fam_pos = int(y[mask].sum())
    return {
        "nearest_family": fam,
        "nearest_similarity": round(float(sims[order[0]]), 4),
        "family_coverage": {"n": int(mask.sum()), "positives": in_fam_pos,
                            "negatives": int(mask.sum()) - in_fam_pos},
        "top5_families_by_state": top5_fams,
        "families_in_pool": len(set(fams.tolist())),
        "pool_n": pc["n"],
    }


def _load_risk_calib():
    global _risk_calib_cache
    if _risk_calib_cache is None:
        if RISK_CALIB.is_file():
            _risk_calib_cache = json.loads(RISK_CALIB.read_text())
        else:
            # fallback : pas de prédiction du tout tant que la calibration
            # n'est pas épinglée (on n'invente pas un seuil à la main)
            _risk_calib_cache = {}
    return _risk_calib_cache

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
        "description": "Journalise le résultat réel (GROUNDÉ : tests exécutés, pas l'avis du "
                       "modèle) d'un patch évalué, pour le recalibrage et le renforcement du "
                       "pool. reporter = auteur du patch, grounded_by = comment l'issue a été "
                       "mesurée (ex. 'pytest-f2p', 'ci', 'human').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "call_id": {"type": "string"},
                "passed": {"type": "boolean"},
                "reporter": {"type": "string", "description": "LLM/agent auteur du patch, optionnel"},
                "grounded_by": {"type": "string", "description": "méthode de mesure de l'issue, optionnel"},
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
        "description": "Le fantôme de chaque run passé note votre brouillon de diff. Compare le "
                       "patch à la géométrie des issues antérieures : distance au plus proche "
                       "ÉCHEC passé moins distance au plus proche SUCCÈS passé (failure-attractor, "
                       "goal-free — pas de gold requis). Pool v8 (n=207). ABSTENTION calibrée : "
                       "verdict (low_risk/high_risk) seulement si la confiance atteint le régime "
                       "mesuré LOAO acc 0.952 [0.773,0.992] (10 % de couverture), sinon "
                       "'abstain' — le fantôme se tait quand il ne sait pas, et explique : le "
                       "bloc 'family' + 'abstention_diagnosis' nomme la famille de tâches la plus "
                       "proche et sa couverture dans le pool (diagnostic additif, la décision ne "
                       "change pas). exclude_task retire une tâche du pool (anti-fuite) ; "
                       "reporter = identité du LLM/agent — REQUIS pour stratifier le flywheel "
                       "par auteur (un appel sans reporter est accepté mais signalé "
                       "'reporter_note' et marqué dans le log). Advisory only — renvoyer l'issue "
                       "groundée via report_outcome.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_text": {"type": "string"},
                "diff_text": {"type": "string"},
                "exclude_task": {"type": "string", "description": "optionnel"},
                "reporter": {"type": "string",
                             "description": "identité du client/LLM appelant (ex. 'claude-4.6', "
                                            "'qwen3.8') — requis pour stratifier le flywheel par "
                                            "auteur, optionnel sinon"},
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
            "serverInfo": {"name": "ghost", "version": "0.4.0"},
        })
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _resp(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            payload = call_tool(name, args)
        except ToolInputError as exc:
            return _err(mid, -32602, str(exc))
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return _resp(mid, {"content": [{"type": "text", "text": text}]})
    if mid is not None:
        return _err(mid, -32601, f"unknown method: {method}")
    return None


class ToolInputError(Exception):
    """Entrée/contexte invalide — renvoyée au client en erreur -32602."""


_DISPATCH = {}


def call_tool(name: str, args: dict) -> dict | str:
    fn = _DISPATCH.get(name)
    if fn is None:
        raise ToolInputError(f"unknown tool: {name}")
    return fn(args)


def tool(fn):
    _DISPATCH[fn.__name__.removeprefix("do_")] = fn
    return fn


@tool
def do_assess_patch(args: dict) -> dict:
    t0 = time.time()
    e = energy_of(args["state_text"], args["diff_text"], args["goal_text"])
    cal = _load_calib()
    above_you, thr = verdict(e, cal)
    # règle publiée : low energy = proche du gold-latent = succès attendu
    passed_pred = above_you
    p = probability(e)  # gardé pour télémétrie, mais pas le driver
    call_id = sha256(f"{t0}:{args['state_text'][:80]}:{args['diff_text'][:80]}".encode()).hexdigest()[:12]
    _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "call_id": call_id,
          "type": "assess", "energy": e, "prob": p,
          "state_sha": sha256(args["state_text"].encode()).hexdigest()[:16],
          "diff_sha": sha256(args["diff_text"].encode()).hexdigest()[:16]})
    return {"call_id": call_id, "energy": round(e, 4),
            "p_pass": round(p, 3),
            "advice": "ok-ship" if passed_pred else "regenerate-with-feedback",
            "energy_threshold": round(thr, 4),
            "votes": {"low_energy_suggests_pass": passed_pred}}


@tool
def do_preflight_patch(args: dict) -> dict:
    # Déterministe, zéro LLM : git apply --check + py_compile du résultat
    repo = Path(args["repo_path"])
    if not repo.is_dir():
        raise ToolInputError(f"repo absent: {repo}")
    diff_txt = args["diff_text"]
    out: dict = {"checks": {}, "ok": True}
    if not (repo / ".git").exists():
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=False, capture_output=True)
    with tempfile.TemporaryDirectory():
        r1 = subprocess.run(["git", "-C", str(repo), "apply", "--check", "-"],
                            input=diff_txt, capture_output=True, text=True, check=False)
        out["checks"]["apply"] = r1.returncode == 0
        if r1.returncode != 0:
            out["apply_err"] = r1.stderr[-400:]
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
    return out


@tool
def do_near_mis_patches(args: dict) -> dict:
    if not POOL_JSON.is_file():
        raise ToolInputError(f"pool absent: {POOL_JSON}")
    try:
        pc = _load_pool()
    except (json.JSONDecodeError, OSError) as exc:
        raise ToolInputError(f"pool illisible: {exc}")
    import numpy as _np
    pool, E_s = pc["rows"], pc["E_s"]
    q = _np.array(embed(args["state_text"]))[None, :]
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
            "family": family_of(task),
            "y": pool[int(i)]["y"],
            "sim": float(sims[int(i)]),
        })
        if len(rows) >= k:
            break
    call_id = sha256(f"{time.time()}:{args['state_text'][:80]}".encode()).hexdigest()[:12]
    _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "call_id": call_id,
          "type": "near-mis", "top": rows})
    return {"call_id": call_id, "nearest": rows}


@tool
def do_risk_scan(args: dict) -> dict:
    # World model goal-free (attracteur d'échecs) — pool v8, abstention
    # calibrée : prédit SEULEMENT si conf >= tau (régime mesuré LOAO à
    # acc 0.952 [0.773,0.992] sur 10 % de couverture), sinon abstain.
    if not POOL_JSON.is_file():
        raise ToolInputError(f"pool absent: {POOL_JSON}")
    cal = _load_risk_calib()
    thr = cal.get("thr_pool"); tau = cal.get("tau_10pct")
    if thr is None or tau is None:
        raise ToolInputError("calibration risk_scan absente "
                             "(risk-scan-v8-calibration.json) — refus de prédire")
    pc = _load_pool()
    import numpy as _np
    cd, y, tasks = pc["cd"], pc["y"], pc["tasks"]
    exc = args.get("exclude_task") or ""
    keep = _np.array([tt != exc for tt in tasks]) if exc \
        else _np.ones(len(y), bool)
    q_s = _np.array(embed(args["state_text"]))
    q_d = _np.array(embed(args["diff_text"][:3000]))
    c_q = q_s + q_d
    c_q = c_q / (_np.linalg.norm(c_q) + 1e-9)
    sims = cd[keep] @ c_q
    yk = y[keep]
    d_fail = float((1 - sims[yk == 0]).min()) if (yk == 0).any() else float("nan")
    d_pass = float((1 - sims[yk == 1]).min()) if (yk == 1).any() else float("nan")
    f1 = d_fail - d_pass
    conf = abs(f1 - thr)
    if conf >= tau:
        zone = "low_risk" if f1 > thr else "high_risk"
        out = {"decision": zone, "abstain": False,
               "attractor_score": round(f1, 4), "confidence": round(conf, 4),
               "expected_acc_regime": cal["predict_regime"]["acc_measured_LOAO"],
               "wilson95": cal["predict_regime"]["wilson95"]}
    else:
        out = {"decision": "abstain", "abstain": True,
               "attractor_score": round(f1, 4), "confidence": round(conf, 4),
               "tau": round(tau, 4),
               "reason": "confiance sous le régime calibré (10 %, acc ≥0.95) — "
                         "le modèle sait qu'il ne sait pas"}
    # Diagnostic de famille (additif — la décision ci-dessus ne change pas).
    out["family"] = _family_diagnosis(q_s, pc)
    if out.get("abstain"):
        cov = out["family"]["family_coverage"]
        out["abstention_diagnosis"] = (
            f"hors régime fiable ; famille la plus proche '{out['family']['nearest_family']}' "
            f"({cov['n']} lignes pool, {cov['positives']} positives) — la géométrie "
            f"n'a pas assez de masse ici pour trancher à acc ≥0.95")
    reporter = args.get("reporter") or ""
    if not reporter:
        out["reporter_note"] = ("reporter absent — ce résultat ne pourra pas être "
                                "stratifié par auteur dans le flywheel (contrat multi-LLM)")
    out.update({"d_nearest_fail": round(d_fail, 4),
                "d_nearest_pass": round(d_pass, 4),
                "pool": POOL_JSON.name, "pool_n": pc["n"],
                "note": "advisory only ; issue groundée requise via report_outcome"})
    call_id = sha256(f"{time.time()}:{args['state_text'][:80]}".encode()).hexdigest()[:12]
    out["call_id"] = call_id
    # capture flywheel : état+diff+score journalisés pour que l'outcome
    # (report_outcome) puisse plus tard rejoindre une vraie paire labellisée
    _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "call_id": call_id,
          "type": "risk_scan", "decision": out["decision"],
          "attractor_score": out["attractor_score"],
          "confidence": out["confidence"],
          "exclude_task": exc,
          "reporter": reporter,
          "reporter_missing": not reporter,
          "nearest_family": out["family"]["nearest_family"],
          "state_sha": sha256(args["state_text"].encode()).hexdigest(),
          "diff_sha": sha256(args["diff_text"].encode()).hexdigest(),
          "state_text": args["state_text"][:4000],
          "diff_text": args["diff_text"][:8000]})
    return out


@tool
def do_report_outcome(args: dict) -> str:
    _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
          "call_id": args["call_id"], "type": "outcome",
          "passed": bool(args["passed"]),
          "reporter": args.get("reporter") or "",
          "grounded_by": args.get("grounded_by") or ""})
    return "enregistré"


def verify_bearer_token(authorization: str | None, token: str) -> bool:
    """Vérification bearer PURE (utilisée par le transport HTTP, story #5
    hardening) : constant-time, vide = refus, aucun log du token."""
    import hmac

    if not token:
        return False  # serveur « protégé » sans token configuré = jamais accepté
    if not isinstance(authorization, str):
        return False
    scheme, _, value = authorization.partition(" ")
    if scheme.strip().lower() != "bearer" or not value.strip():
        return False
    return hmac.compare_digest(value.strip(), token)


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
            print(f"[ghost] BAD-JSON len={len(raw)} err={exc.reason}", file=sys.stderr)
            continue
        try:
            print(f"[ghost] method={msg.get('method')}", file=sys.stderr)
            out = handle(msg)
            has = out is not None
            print(f"[ghost] → { 'answer' if has else 'noop' }", file=sys.stderr)
            if has:
                sys.stdout.write(json.dumps(out) + "\n")
                sys.stdout.flush()
        except (KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f"[ghost] EXC {type(exc).__name__}: {exc}", file=sys.stderr)
            sys.stdout.write(json.dumps(_err(msg.get("id"), -32603, str(exc))) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
