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

v0.5.1 (2026-08-16) : abstention NOMMÉE TS/monorepo (story 14.4 issue B) —
une requête au signal TS qui s'abstient porte `named_non_coverage` explicite
(« hors couverture connue »), pas une abstention générique silencieuse.

v0.5.0 (2026-08-16) : abstention CONFORME Mondrian par famille (story 12.2) —
v0.6.0 (2026-08-17) : MIGRATION ENCODEUR — le pool servi peut tourner sous
jina-v2-base-code (bras 3b345cdd : pooled4 PROMOUVABLE 0.7428 [0.640,0.840]).
Chaque réponse porte désormais `encoder` (env LI_ENCODER) — la géométrie des
espaces unixcoder et jina est INCOMPATIBLE : pool/calibration/encoder forment
un triplet indivisible (drop-in pool-v11.conf embarque les trois).
LI_CONFORMAL_CALIB posée ⇒ seuil par strate avec garantie « erreur ≤ 10 % parmi
les réponses retenues » (repli pooled disclosé si strate insuffisante) ;
variable absente ⇒ régime tau-fixe legacy (rollback = 1 config). Chaque réponse
nomme served_regime + calibration_served + disclosures (truncation 3000 chars).

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ghost_compare import (
    calibrate_local,
    goal_free_scores,
    informative_selection,
)

ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = Path(os.environ.get(
    "LI_CALIBRATION",
    ROOT / "governance" / "act2" / "arm-artifacts" / "predictor-mcp-calibration.json"))
LOG_PATH = Path(os.environ.get(
    "LI_LOG_PATH",
    ROOT / "data" / "landing" / "act2-pilot" / "mcp-log.jsonl"))
# pool servi : v8 (n=207) par défaut — surchargable par env pour tests/reculs
PERTEST_PATH = Path(os.environ.get("LI_PERTEST_MODEL", ""))  # v0.8.0 : vide = colonne per-test désactivée
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


def _embedder_family(encoder: str) -> str:
    """v0.6.0 : la requête DOIT être encodée dans le même espace que le pool
    servi (espaces incompatibles — prereg migration 3b345cdd)."""
    return "jina" if "jina" in encoder.lower() else "unixcoder"


def _ensure_model():
    global _model, _tok
    if _model is None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from transformers import AutoModel, AutoTokenizer
        if _embedder_family(ENCODER) == "jina":
            import torch
            import transformers as _tf

            def _fphi(heads, n_heads, head_size, already_pruned_heads):
                mask = torch.ones(n_heads, head_size)
                heads = set(heads) - already_pruned_heads
                for h in heads:
                    h -= sum(1 if oh < h else 0 for oh in already_pruned_heads)
                    mask[h] = 0
                mask = mask.view(-1).contiguous().eq(1)
                return heads, torch.arange(mask.size(0))[mask].long()

            _tf.pytorch_utils.find_pruneable_heads_and_indices = _fphi
            if not hasattr(_tf.PreTrainedModel, "get_head_mask"):
                _tf.PreTrainedModel.get_head_mask = (
                    lambda self, head_mask, num_hidden_layers, is_attention_chunked=False:
                    [None] * num_hidden_layers)
            from transformers import AutoConfig
            cid = "jinaai/jina-embeddings-v2-base-code"
            cfg = AutoConfig.from_pretrained(cid, trust_remote_code=True)
            for a, v in (("is_decoder", False), ("use_cache", False),
                         ("is_encoder_decoder", False), ("tie_word_embeddings", False),
                         ("add_cross_attention", False), ("chunk_size_feed_forward", 0),
                         ("cross_attention_hidden_size", None)):
                if not hasattr(cfg, a):
                    setattr(cfg, a, v)
            _tok = AutoTokenizer.from_pretrained(cid, trust_remote_code=True)
            _model = AutoModel.from_pretrained(cid, config=cfg, trust_remote_code=True).eval()
        else:
            _tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
            _model = AutoModel.from_pretrained("microsoft/unixcoder-base").eval()


def embed(text: str):
    _ensure_model()
    import numpy as np
    fam = _embedder_family(ENCODER)
    torch = __import__("torch")
    tb = _tok([text], padding=True, truncation=True,
              max_length=8192 if fam == "jina" else 512, return_tensors="pt")
    kw = {"token_type_ids": torch.zeros_like(tb["input_ids"])} if fam == "jina" else {}
    with torch.no_grad():
        lh = _model(**tb, **kw).last_hidden_state
        if fam == "jina":  # pooling last-token natif jina-v2
            idx = tb["attention_mask"].sum(1) - 1
            h = lh[0, int(idx[0])]
        else:
            h = lh[0, 0]
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


# ---------------- per-test (DW-48, arm 3896a3e7 VALIDÉ) ----------------

_PERTEST = None
_TEST_EMB_CACHE: dict[str, list[float]] = {}


def _load_pertest():
    global _PERTEST
    if _PERTEST is not None:
        return _PERTEST
    if not PERTEST_PATH or not Path(PERTEST_PATH).is_file():
        _PERTEST = False
        return _PERTEST
    import numpy as np

    d = np.load(PERTEST_PATH)
    pt = {"w": d["w"].astype("float64"), "b": float(d["b"]),
          "threshold": float(d["threshold"]), "lam": float(d.get("lam", 0.01))}
    if "cal_x" in d.files:  # DW-48(a) : recalibration isotonique arm 47273883
        pt["cal_x"] = d["cal_x"].astype("float64")
        pt["cal_p"] = d["cal_p"].astype("float64")
    _PERTEST = pt
    return _PERTEST


def embed_batch(texts: list[str]):
    """DW-48(b) latence : un seul forward pour N textes (protocole identique
    à embed() : même troncation, même pooling, token_type_ids=0 pour jina)."""
    import numpy as np
    import torch

    _ensure_model()
    fam = _embedder_family(ENCODER)
    tb = _tok(texts, padding=True, truncation=True,
              max_length=8192 if fam == "jina" else 512, return_tensors="pt")
    kw = {"token_type_ids": torch.zeros_like(tb["input_ids"])} if fam == "jina" else {}
    with torch.no_grad():
        lh = _model(**tb, **kw).last_hidden_state
    if fam == "jina":
        idx = (tb["attention_mask"].sum(1) - 1).long()
        h = lh[torch.arange(len(texts)), idx]
    else:
        h = lh[:, 0, :]
    A = h.numpy().astype(np.float64)
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def _test_embeddings(names: list[str]):
    """Cache inter-processus des embeddings de noms de tests (stables) ;
    les absents sont embeddés EN BATCH (un forward, pas un par nom)."""
    import numpy as np

    missing = [n for n in names if n not in _TEST_EMB_CACHE]
    if missing:
        vecs = embed_batch(missing)
        room = 4096 - len(_TEST_EMB_CACHE)
        for n, v in zip(missing[:max(0, room)], vecs[:max(0, room)]):
            _TEST_EMB_CACHE[n] = v.tolist()
    return {n: np.array(_TEST_EMB_CACHE[n]) for n in names}


def _calibrate(p: float, pt: dict) -> float:
    if "cal_x" not in pt:
        return p
    import numpy as np

    return float(np.interp(p, pt["cal_x"], pt["cal_p"],
                           left=float(pt["cal_p"][0]), right=float(pt["cal_p"][-1])))


def predict_failing_tests(diff_text: str, declared_tests: list) -> dict:
    """Colonne v2 : pour chaque test déclaré, P(reste rouge | patch).
    Modèle logistique L2 sur [E_diff||E_test||cos] arm 3896a3e7 (VALIDÉ),
    probas recalibrées isotoniquement (arm 47273883, DW-48a).
    ABSTENTION si pas de tests déclarés ou pas de modèle (jamais de devinette)."""
    import math

    import numpy as np
    pt = _load_pertest()
    if not pt:
        return {"status": "unavailable", "reason": "LI_PERTEST_MODEL absent",
                "tests": []}
    if not declared_tests:
        return {"status": "abstained", "reason": "no declared tests", "tests": []}
    Ed = embed(diff_text[:8000])  # troncature identique au dataset d'entraînement
    names = [t.strip() for t in declared_tests if isinstance(t, str) and t.strip()]
    if not names:
        return {"status": "abstained", "reason": "no declared tests", "tests": []}
    embs = _test_embeddings(names)
    rows = []
    for t in names:
        Et = embs[t]
        x = np.concatenate([Ed, Et, [float(Ed @ Et)]])
        p_raw = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, float(pt["w"] @ x + pt["b"])))))
        p = _calibrate(p_raw, pt)
        rows.append({"test": t.strip(), "p_failing": round(p, 4),
                     "predicted_red": bool(p >= pt["threshold"])})
    return {"status": "measured",
            "model": {"kind": "logistic-L2-pair", "prereg": "3896a3e750a37f1d",
                      "calibration": "isotonic-PAV-LOO" if "cal_x" in pt else "raw-sigmoid",
                      "calibration_prereg": "4727388318599f06" if "cal_x" in pt else None,
                      "lambda": pt["lam"], "threshold": pt["threshold"],
                      "disclosure": "seuil Youden sur probas recalibrées LOO ; "
                      "une proba par test, signal additif — jamais un verdict"},
            "tests": rows}


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
_conformal_cache = None

# Story 12.2 : calibration conforme servie à côté du pool pour audit client.
CONFORMAL_CALIB = Path(os.environ.get(
    "LI_CONFORMAL_CALIB", ""))  # vide ⇒ régime tau-fixe legacy (rollback 1 config)
ENCODER = os.environ.get("LI_ENCODER", "microsoft/unixcoder-base")  # v0.6.0


def family_of(task: str) -> str:
    """Dérivation MÉCANIQUE de la famille d'une tâche : le préfixe avant le
    premier point (owner__repo). Zéro modèle, zéro apprentissage — c'est une
    dérivation déterministe, pas une classification (leçon S11 : la famille
    et l'auteur sont des facteurs de première classe; on les expose, on ne
    les invente pas)."""
    t = str(task)
    for sep in (".", ":"):  # flywheel:<hash> => famille « flywheel » (cohérence
        if sep in t:        # Mondrian : la calibration stratifie sur ce préfixe)
            return t.split(sep, 1)[0]
    return t


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


# Registre des strates TS/monorepo CONNUES hors pool (fenêtres archivées —
# mécanique, disclosé : coverage-ts-1 archivée 2026-08-16, gate dégénérée).
KNOWN_TS_FAMILIES = frozenset({"acre__blocks"})

_TS_MARKERS = (".ts", ".tsx", ".cts", ".mts", "apps/front", "apps/api",
               "from \"react\"", "from 'react'", "next/")


def ts_flavor(state_text: str, diff_text: str) -> bool:
    """Signal TS/monorepo dans la requête (heuristique conservative, additive —
    ne change JAMAIS la décision ; story 14.4 issue B : nommer la non-couverture)."""
    blob = ((state_text or "") + "\n" + (diff_text or "")).lower()
    return any(m in blob for m in _TS_MARKERS)


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


def _load_conformal():
    global _conformal_cache
    if _conformal_cache is None:
        if CONFORMAL_CALIB and Path(CONFORMAL_CALIB).is_file():
            _conformal_cache = json.loads(Path(CONFORMAL_CALIB).read_text())
        else:
            _conformal_cache = {}
    return _conformal_cache


def conformal_tau(cal: dict, nearest_family: str, alpha: str = "alpha_0.10") -> dict:
    """Choix du seuil conforme servi (pur, testable sans pool ni embed).

    Mondrian : si la strate famille a une garantie (n ≥ N_MIN) ⇒ τ_g ; sinon le
    seuil GLOBAL avec disclosure « données insuffisantes pour une garantie par
    famille » (honest emptiness — jamais de garantie fabriquée, FR-27)."""
    strata = cal.get("strata_mondrian", {})
    st = strata.get(nearest_family, {}).get(alpha)
    if st and st.get("tau") is not None and st["tau"] != float("inf"):
        return {"tau": st["tau"], "stratum": nearest_family,
                "guarantee": st["guarantee"],
                "n_stratum": st["n"],
                "realized_err_rate": st.get("realized_err_rate"),
                "source": "mondrian-family"}
    gl = cal.get("global_conformal", {}).get(alpha) or {}
    if gl.get("tau") is not None:
        return {"tau": gl["tau"], "stratum": nearest_family,
                "guarantee": gl.get("guarantee"),
                "n_stratum": (strata.get(nearest_family, {}).get(alpha) or {}).get("n"),
                "realized_err_rate": gl.get("realized_err_rate"),
                "source": "global-pooled (stratum familial n≥N_MIN insuffisant : "
                          "la garantie publiée est celle du pool entier, pas de la famille)"}
    return {}


def _family_of_query(q_s, pc) -> str:
    """Famille de la requête = famille pool la plus proche en espace E_state
    (même dérivation que le diagnostic additif — déterministe, numpy pur)."""
    import numpy as _np
    E_s, fams = pc["E_s"], pc["families"]
    q = q_s / (_np.linalg.norm(q_s) + 1e-9)
    sims = E_s @ q
    return str(fams[int(_np.argmax(sims))])


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
        "name": "compare_patches",
        "description": "Ghost PR-Simulator : compare K patchs candidats sur un même "
                       "problème. Phase 1 (issues < 8) : retourne un plan d'exécution "
                       "(les n patchs à tester réellement en priorité) SANS recommandation. "
                       "Phase 2 (issues >= 8 fournis par l'appelant, groundés par exécution "
                       "réelle des tests) : calibration locale conforme => recommandation, "
                       "probabilités, abstentions, disclosures. Ghost n'exécute jamais les "
                       "tests lui-même : l'issue vient de l'appelant (grounded_by requis).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidates": {"type": "array", "description": "K patchs candidats",
                               "items": {"type": "object", "properties": {
                                   "id": {"type": "string"},
                                   "state_text": {"type": "string", "description": "problème/symptômes + noms de tests qui doivent passer"},
                                   "diff_text": {"type": "string"}},
                                   "required": ["id", "state_text", "diff_text"]}},
                "budget_n": {"type": "integer", "description": "nombre d'exécutions réelles ciblées (défaut 8, minimum produit)", "default": 8},
                "issues": {"type": "object", "description": "{id: {y: 0|1, grounded_by: str}} — issues mesurées RÉELLEMENT (tests exécutés par l'appelant)", "default": {}},
                "declared_tests": {"type": "array", "items": {"type": "string"},
                    "description": "v2 (DW-48) : noms des tests déclarés à l'avance — Ghost "
                                   "retourne pour chaque candidat P(test reste rouge). "
                                   "Absent/vide => abstention de la colonne.", "default": []},
                "reporter": {"type": "string"},
            },
            "required": ["candidates"],
        },
    },
    {
        "name": "risk_scan",
        "description": "Le fantôme de chaque run passé note votre brouillon de diff. Compare le "
                       "patch à la géométrie des issues antérieures : distance au plus proche "
                       "ÉCHEC passé moins distance au plus proche SUCCÈS passé (failure-attractor, "
                       "goal-free — pas de gold requis). ABSTENTION CONFORME (GHOST v0.5.0) : "
                       "verdict (low_risk/high_risk) seulement si la confiance atteint le seuil "
                       "conforme de la strate — garantie distribution-free « taux d'erreur ≤ 10 % "
                       "parmi les réponses retenues », Mondrian par famille quand la strate a "
                       "assez de lignes, repli pooled disclosé sinon ; chaque réponse nomme son "
                       "régime (served_regime) et la calibration servie (calibration_served) "
                       "auditable par le client. DISCLOSURE : diff_text est tronqué à 3000 "
                       "caractères avant embedding (signalé dans 'disclosures' quand ça arrive). "
                       "Sinon 'abstain' — le fantôme se tait quand il ne sait pas, et explique : "
                       "le bloc 'family' + 'abstention_diagnosis' nomme la famille de tâches la "
                       "plus proche et sa couverture dans le pool (diagnostic additif, la décision "
                       "ne change pas). exclude_task retire une tâche du pool (anti-fuite) ; "
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
            "serverInfo": {"name": "ghost", "version": "0.8.0"},
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
    conf_cal = _load_conformal()
    serv_regime = "conformal-mondrian" if conf_cal else "fixed-tau"
    import numpy as _np
    cd, y, tasks = pc["cd"], pc["y"], pc["tasks"]
    exc = args.get("exclude_task") or ""
    keep = _np.array([tt != exc for tt in tasks]) if exc \
        else _np.ones(len(y), bool)
    q_s = _np.array(embed(args["state_text"]))
    diff_in = args["diff_text"]
    diff_truncated = len(diff_in) > 3000
    q_d = _np.array(embed(diff_in[:3000]))
    c_q = q_s + q_d
    c_q = c_q / (_np.linalg.norm(c_q) + 1e-9)
    sims = cd[keep] @ c_q
    yk = y[keep]
    d_fail = float((1 - sims[yk == 0]).min()) if (yk == 0).any() else float("nan")
    d_pass = float((1 - sims[yk == 1]).min()) if (yk == 1).any() else float("nan")
    f1 = d_fail - d_pass
    conf = abs(f1 - thr)
    conformal = conformal_tau(conf_cal, _family_of_query(q_s, pc)) if conf_cal else {}
    eff_tau = conformal.get("tau", tau)
    if conf >= eff_tau:
        zone = "low_risk" if f1 > thr else "high_risk"
        out = {"decision": zone, "abstain": False,
               "attractor_score": round(f1, 4), "confidence": round(conf, 4)}
        if conformal:
            out["conformal"] = {
                "tau_stratum": round(conformal["tau"], 4),
                "stratum": conformal["stratum"],
                "guarantee": conformal["guarantee"],
                "realized_err_rate_replay": conformal.get("realized_err_rate"),
                "source": conformal["source"]}
        else:
            out.update({"expected_acc_regime": cal["predict_regime"]["acc_measured_LOAO"],
                        "wilson95": cal["predict_regime"]["wilson95"]})
    else:
        out = {"decision": "abstain", "abstain": True,
               "attractor_score": round(f1, 4), "confidence": round(conf, 4),
               "tau": round(eff_tau, 4),
               "reason": ("confiance sous le seuil conforme (garantie ≤10 % d'erreur "
                          "si retenue)" if conformal else
                          "confiance sous le régime calibré (10 %, acc ≥0.95)") +
                         " — le modèle sait qu'il ne sait pas"}
        if conformal:
            out["conformal"] = {"tau_stratum": round(conformal["tau"], 4),
                                "stratum": conformal["stratum"],
                                "guarantee": conformal["guarantee"],
                                "source": conformal["source"]}
    # Diagnostic de famille (additif — la décision ci-dessus ne change pas).
    out["family"] = _family_diagnosis(q_s, pc)
    if out.get("abstain"):
        cov = out["family"]["family_coverage"]
        out["abstention_diagnosis"] = (
            f"hors régime fiable ; famille la plus proche '{out['family']['nearest_family']}' "
            f"({cov['n']} lignes pool, {cov['positives']} positives) — la géométrie "
            f"n'a pas assez de masse ici pour trancher à acc ≥0.95")
    # Issue B (14.4) : abstention NOMMÉE pour le travail TS/monorepo — pas
    # d'abstention générique quand la famille est connue hors couverture.
    if out.get("abstain") and ts_flavor(args.get("state_text", ""), args.get("diff_text", "")):
        pool_fams = set(pc["families"].tolist())
        ts_covered = pool_fams & KNOWN_TS_FAMILIES
        if not ts_covered:
            out["named_non_coverage"] = (
                "famille TS/monorepo hors couverture connue — aucune strate TS "
                "dans le pool servi (coverage-ts-1 archivée 2026-08-16 : gate "
                "poison dégénérée, quota non mixé). Le fantôme NE PEUT PAS "
                "trancher sur ce terrain ; diagnostic additif, décision inchangée.")
    reporter = args.get("reporter") or ""
    if not reporter:
        out["reporter_note"] = ("reporter absent — ce résultat ne pourra pas être "
                                "stratifié par auteur dans le flywheel (contrat multi-LLM)")
    out.update({"d_nearest_fail": round(d_fail, 4),
                "d_nearest_pass": round(d_pass, 4),
                "pool": POOL_JSON.name, "pool_n": pc["n"], "encoder": ENCODER,
                "served_regime": serv_regime,
                "calibration_served": (Path(CONFORMAL_CALIB).name if conf_cal
                                       else RISK_CALIB.name),
                "disclosures": ["advisory only — issue groundée requise via report_outcome"]
                + ([f"diff_text tronqué à 3000 caractères avant embedding (reçu {len(diff_in)} chars)"]
                   if diff_truncated else []),
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
def do_compare_patches(args: dict) -> dict:
    """Ghost PR-Simulator (v0.8.0) : plan d'exécution (n<8) ou recommandation
    calibrée conforme (n>=8 issues réelles fournies par l'appelant) + colonne
    per-test « tests prédits échoués » (DW-48, arm 3896a3e7 VALIDÉ)."""
    import importlib.util

    import numpy as _np
    cands = args.get("candidates") or []
    declared = args.get("declared_tests") or []
    if not cands or any(not c.get("id") or not c.get("diff_text") for c in cands):
        raise ToolInputError("candidates requis : [{id, state_text, diff_text}] non vides")
    n_min = 8
    budget = int(args.get("budget_n") or n_min)
    issues_in = args.get("issues") or {}
    issues = {}
    for cid, iss in issues_in.items():
        yv = iss.get("y") if isinstance(iss, dict) else iss
        if yv in (0, 1):
            issues[cid] = int(yv)
    bad = [c for c in issues if c not in {x["id"] for x in cands}]
    if bad:
        raise ToolInputError(f"issues inconnues hors candidats : {bad[:3]}")
    _spec = importlib.util.spec_from_file_location(
        "s11c", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
    s11c = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(s11c)
    pc = _load_pool()
    ids = [c["id"] for c in cands]
    E_cand = _np.vstack([s11c.norm(
        _np.array([(embed(c.get("state_text", "")[:1200]) +
                    embed(c["diff_text"][:3000])) / 2.0])) for c in cands])
    scores = goal_free_scores(pc["cd"], pc["y"], pc["tasks"], E_cand, s11c)
    out = {"tool": "compare_patches", "pool": POOL_JSON.name, "encoder": ENCODER,
           "n_candidates": len(ids), "n_min_recommend": n_min,
           "n_issues_mesurees": len(issues),
           "grounded_by": {cid: (issues_in[cid].get("grounded_by") if isinstance(issues_in.get(cid), dict) else None)
                           for cid in issues}}
    out["predicted_failing_tests"] = {
        c["id"]: predict_failing_tests(c["diff_text"], declared) for c in cands}
    if len(issues) < n_min and len(issues) < len(ids):
        # plan d'exécution seulement s'il RESTE des candidats non mesurés ;
        # sinon (tous mesurés) la calibration répond en régime fully-measured
        plan = informative_selection(ids, scores, max(budget, n_min) - len(issues))
        out.update({"phase": "execution-plan",
                    "execution_plan": plan,
                    "disclosure": (f"{len(issues)}/{n_min} issues réelles : AUCUNE recommandation "
                                   "possible (règle produit mesurée en démo 15.4 : sous n=8, le "
                                   "prior global ne distingue pas des candidats proches — G1 0/4). "
                                   "Exécutez réellement les tests des patchs listés (les plus "
                                   "informatifs selon le prior), puis rappelez avec issues={id:{y,grounded_by}}.")})
        return out
    E_issues = {cid: E_cand[ids.index(cid)] for cid in issues}
    cal = calibrate_local(pc["cd"], pc["y"], E_issues, issues, E_cand, ids, s11c,
                          alpha=0.10, n_min=n_min)
    rec = cal.get("recommendation")
    out.update({"phase": "recommendation" if rec else "abstention",
                "calibration": cal})
    if cal.get("regime") in ("local", "fully-measured"):
        for c in out["calibration"]["candidates"]:
            c["prior_score"] = round(scores[ids.index(c["id"])], 4)
    out["warning"] = ("advisory only — la recommandation est une comparaison calibrée, "
                      "jamais une garantie ; issue réelle requise via report_outcome ; "
                      "colonne per-test = signal additif, proba par test, DW-48")
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
