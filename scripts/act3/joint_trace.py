#!/usr/bin/env python3
"""Story 13.4 — espace joint diff × trace-tests (0 appel).

Chaque ligne du pool qui a une trace docker réelle (run-result.json issu des
labelisations) gagne un vecteur trace ; les autres sont zero-padded avec
DISCLOSURE (pas de trace inventée). Évaluation LOFO en retrieval ASYMÉTRIQUE :
les requêtes (fold held-out) n'ont JAMAIS de trace au serving-time réel — on
les mesure donc zero-padded contre un pool qui en porte, ce qui est l'implication
de serving demandée par l'AC, énoncée explicitement dans l'artefact.

Composition ÉPINGLÉE pré-run (pas de recherche) :
  cd_joint = norm( [cd ; ctrace] )  — concaténation simple 768+768, les deux
  composantes déjà normalisées. Pas de pondération apprise.

Étapes : (1) join local traces → traces.jsonl ; (2) embed node (unixcoder) →
latent-pool-v10-joint.npz ; (3) ext-LOAO + in-family vs gates 13.1.
Run: uv run python scripts/act3/joint_trace.py [--stage join|measure]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
OUT = ROOT / "governance" / "act2" / "arm-artifacts" / "ext-loao-candidate-joint-v10.json"
TRACES = PILOT / "latent-pool-v10-traces.jsonl"
JOINT_NPZ = PILOT / "latent-pool-v10-joint.npz"

_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)


def _trace_for(task: str, campaign: str, arm: str) -> str | None:
    key = task.replace("/", "_")
    cands = []
    if campaign in ("frozen32", "extension-128"):
        base = PILOT / "extension-128" / "results" if campaign == "extension-128" else PILOT / "results"
        cands += [base / f"{key}-{arm}" / "run-result.json",
                  base / f"{key}-off" / "run-result.json",
                  base / f"{key}-on" / "run-result.json"]
    elif campaign == "s12-gen":
        for d in (PILOT / "s12-gen" / "results").glob(f"{key}-d*"):
            cands.append(d / "run-result.json")
    elif campaign == "s14-gen":
        for d in (PILOT / "s14-gen" / "results").glob(f"{key}*"):
            cands.append(d / "run-result.json")
    for c in cands:
        if c.is_file():
            try:
                rr = json.loads(c.read_text())
            except json.JSONDecodeError:
                continue
            parts = [rr.get("f2p_tail") or "", rr.get("p2p_tail") or ""]
            txt = "\n".join(p for p in parts if p.strip())
            if txt.strip():
                return txt[:4000]
    return None


def stage_join() -> int:
    rows = json.loads((PILOT / "latent-pool-v10.json").read_text())
    n_with = 0
    with TRACES.open("w") as fh:
        for r in rows:
            t = _trace_for(r["task"], r.get("campaign", ""), r.get("arm", ""))
            if t:
                n_with += 1
            else:
                t = ""  # zero-pad : absence réelle, pas une trace inventée
            fh.write(json.dumps({"task": r["task"], "trace": t}) + "\n")
    print(f"join: {n_with}/{len(rows)} lignes avec trace docker réelle "
          f"({len(rows) - n_with} zero-padded disclosés) → {TRACES.name}")
    return 0


def family_of(task: str) -> str:
    for sep in (".", ":"):
        if sep in task:
            return task.split(sep, 1)[0]
    return task


def stage_measure() -> int:
    pool = "v10"
    rows = json.loads((PILOT / f"latent-pool-{pool}.json").read_text())
    d = np.load(PILOT / f"latent-pool-{pool}.npz")
    dj = np.load(JOINT_NPZ)
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    fams = np.array([family_of(t) for t in tasks])
    cd = s11.norm(s11.norm(d["E_state"]) + s11.norm(d["E_diff"]))
    cdj = dj["E_joint"]
    has_trace = dj["has_trace"].astype(bool)

    def ext_loao_on(M, query_M):
        scores = np.full(len(y), np.nan)
        preds = np.full(len(y), -1)
        for g in sorted(set(fams)):
            te = fams == g
            tr = ~te
            if not y[tr].any() or y[tr].all():
                continue
            pos, neg = M[tr][y[tr] == 1], M[tr][y[tr] == 0]
            str_ = (1 - M[tr] @ neg.T).min(1) - (1 - M[tr] @ pos.T).min(1)
            thr = float(np.median(str_))
            q = (1 - query_M[te] @ neg.T).min(1) - (1 - query_M[te] @ pos.T).min(1)
            scores[te] = q
            preds[te] = (q > thr).astype(int)
        valid = ~np.isnan(scores)
        auc = s11.auc(scores[valid][y[valid] == 1], scores[valid][y[valid] == 0])
        acc = float((preds[valid] == y[valid]).mean())
        return auc, acc, int(valid.sum()), scores

    # requêtes ZERO-PADDED dans l'espace joint (asymétrie serving : la requête
    # n'a jamais de trace) — même dimensionnalité que le pool joint
    qz = np.concatenate([cd, np.zeros((len(cd), cd.shape[1]))], axis=1)
    qz = qz / (np.linalg.norm(qz, axis=1, keepdims=True) + 1e-9)
    auc_j, acc_j, n_j, _ = ext_loao_on(cdj, qz)  # requêtes SANS trace
    auc_i, acc_i, n_i, _ = ext_loao_on(cd, cd)   # rappel baseline sur mêmes folds
    f1_in = s11._loao_f1_features(cd, tasks, y)
    auc_in = s11.auc(f1_in[y == 1], f1_in[y == 0])

    BASE_EXT, MARGIN, HOME_GUARD = 0.5477, 0.05, 0.6694 - 0.02
    pass_transfer = bool(auc_j >= BASE_EXT + MARGIN)
    pass_home = bool(auc_in >= HOME_GUARD)
    verdict = ("FRANCHIT les gates — enregistré pour validation prospective"
               if (pass_transfer and pass_home) else
               "SOUS LA GATE — résultat négatif publié, non promu")

    report = {
        "story": "13.4-joint-diff-trace",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "pool": f"latent-pool-{pool}",
        "pool_sha256_16": sha256(
            (PILOT / f"latent-pool-{pool}.json").read_bytes()).hexdigest()[:16],
        "composition_pinned": "cd_joint = norm([cd; ctrace]) — concaténation "
                              "souple 768+768, composantes normalisées, zéro "
                              "pondération apprise (épinglé pré-run)",
        "trace_coverage": {"rows_with_real_trace": int(has_trace.sum()),
                           "rows_zero_padded": int((~has_trace).sum()),
                           "zero_pad_disclosure": "absence de trace = vecteur nul ; "
                                                  "jamais de trace inventée (FR-3)"},
        "serving_asymmetry": "les traces n'existent QUE pour les lignes du pool, "
                             "jamais pour la requête : l'évaluation requête "
                             "zero-padded contre pool joint EST la condition de "
                             "serving — mesurée telle quelle, pas contournée",
        "candidate": {
            "ext_loao_joint": {"auc": round(auc_j, 4), "acc": round(acc_j, 4),
                               "n_evaluated": n_j},
            "ext_loao_baseline_same_folds": {"auc": round(auc_i, 4),
                                             "acc": round(acc_i, 4), "n_evaluated": n_i},
            "in_family_loao": {"auc": round(auc_in, 4)},
        },
        "gates_sealed_13_1": {"baseline_ext": BASE_EXT, "margin": MARGIN,
                              "transfer_threshold": BASE_EXT + MARGIN,
                              "home_guard": round(HOME_GUARD, 4),
                              "pass_transfer": pass_transfer, "pass_home": pass_home},
        "verdict": verdict,
        "serving": "non servi — géométrie v10 inchangée (prospective-only, S13)",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"joint ext-LOAO: AUC {auc_j:.4f} acc {acc_j:.4f} (gate ≥ {BASE_EXT+MARGIN}) "
          f"| in-family {auc_in:.4f} | traces: {int(has_trace.sum())}/{len(y)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("join", "measure"), required=True)
    a = ap.parse_args()
    sys.exit(stage_join() if a.stage == "join" else stage_measure())
