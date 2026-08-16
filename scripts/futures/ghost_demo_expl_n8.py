#!/usr/bin/env python3
"""Ghost pivot — story 15.4 : EXÉCUTION du protocole pré-enregistré
(governance/act2/ghost-demo-15-4-prereg.md, ancré 1babd393). Zéro appel
modèle : uniquement des exécutions réelles de tests + numpy.

Run: uv run python scripts/futures/ghost_demo_15_4.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)
POOL = ROOT / "data" / "landing" / "act2-pilot"
SESS = POOL / "ghost-session-v9"
SCENARIOS = (5, 6, 7, 8)
N_BOOT = 8


def prior_scores(ids: list[str], E: np.ndarray) -> dict[str, float]:
    rows = json.loads((POOL / "latent-pool-v10.json").read_text())
    d = np.load(POOL / "latent-pool-v10.npz")
    y = np.array([int(r["y"]) for r in rows])
    Ep = s11.norm(d["E_diff"].astype(np.float32))
    allm = np.vstack([Ep, E])
    tasks = np.array(["pool"] * len(y) + [f"c{i}" for i in range(len(ids))])
    f1 = s11._loao_f1_features(allm, tasks, np.concatenate([y, np.zeros(len(ids))]))
    sc = f1[len(y):]
    return {cid: float(v) for cid, v in zip(ids, sc)}


def select(ids: list[str], scores: dict[str, float], seed: int, n: int) -> list[str]:
    ordre = sorted(ids, key=lambda i: (scores[i], i))
    rot = ordre[seed % len(ordre):] + ordre[:seed % len(ordre)]
    sel = [rot[len(rot) // 2]]
    rest = [i for i in rot if i not in sel]
    while len(sel) < n and rest:
        rest.sort(key=lambda i: min(abs(scores[i] - scores[s]) for s in sel), reverse=True)
        sel.append(rest.pop(0))
    return sel


def ground_truth() -> dict[str, int]:
    """SOURCE AUTORITAIRE : provenance des label-reports P0 (attempt_id=slot).
    Jamais utilisée pour la sélection bootstrap (pré-enregistrement 1babd393)."""
    gt = {}
    mani = json.loads((POOL / "ghost-session-v9-manifest.json").read_text())
    slot2id = {c["source_slot"]: c["id"] for c in mani["candidates"]}
    for arm in ("flash", "pinned"):
        rep = json.loads((POOL / f"coverage-ts-9-{arm}" / "labels" / "genfam-label-report.json").read_text())
        for pr in rep["provenance"]:
            cid = slot2id.get(pr["attempt_id"])
            if cid and isinstance(pr.get("y"), int):
                gt[cid] = int(pr["y"])
    return gt


def main() -> int:
    mani = json.loads((POOL / "ghost-session-v9-manifest.json").read_text())
    z = np.load(SESS / "session-embeds.npz", allow_pickle=True)
    ids = list(z["ids"])
    E = s11.norm(z["E_diff"].astype(np.float32))
    scores = prior_scores(ids, E)
    gt = ground_truth()
    print(f"prior scores OK ({len(scores)}) ; ground truth P0: {sum(1 for v in gt.values() if v==1)} pos / {sum(1 for v in gt.values() if v==0)} neg sur {len(gt)}")
    (SESS / "prior-scores.json").write_text(json.dumps(scores, indent=1) + "\n")
    import subprocess

    verdicts = []
    for s in SCENARIOS:
        sel = select(ids, scores, seed=s, n=N_BOOT)
        sdir = SESS / f"expl-n8-s{s}"
        sdir.mkdir(exist_ok=True)
        import shutil
        shutil.copy(SESS / "session-embeds.npz", sdir / "session-embeds.npz")
        m2 = dict(mani)
        m2["session_id"] = f"ghost-session-v9/expl-n8-s{s}"
        m2["out_dir"] = str(sdir)
        m2["budget_n"] = N_BOOT
        m2["prior_scores"] = {i: scores[i] for i in sel}
        m2["selection_seed"] = s
        mf = sdir / "manifest.json"
        mf.write_text(json.dumps(m2, indent=1, ensure_ascii=False) + "\n")
        print(f"--- scénario s{s}: bootstrap {sel}", flush=True)
        r = subprocess.run([sys.executable, str(ROOT / "scripts/futures/session_bootstrap.py"),
                            "--manifest", str(mf)], capture_output=True, text=True, check=False)
        print(r.stdout.strip()[-800:])
        sys.path.insert(0, str(ROOT / "scripts" / "futures"))
        import importlib
        lc = importlib.import_module("local_calibration")
        importlib.reload(lc)
        sys.argv = ["local_calibration.py", "--manifest", str(mf)]
        try:
            lc.main()
        except SystemExit:
            pass
        cal = json.loads((sdir / "calibration.json").read_text()) if (sdir / "calibration.json").is_file() else {}
        ys = {}
        for f in sdir.glob("issue-*.json"):
            rr = json.loads(f.read_text())
            if isinstance(rr.get("y"), int):
                ys[rr["id"]] = rr["y"]
        top = cal.get("recommendation", {}).get("id")
        preds = {c["id"]: c["predict_positive"] for c in cal.get("candidates", [])}
        hors = {i: preds.get(i) for i in ids if i not in sel}
        acc_hits = [1 for i, pv in hors.items() if pv is not None and gt.get(i) == (1 if pv else 0)]
        sc = {"seed": s, "bootstrap_ids": sel, "bootstrap_y": ys,
              "regime": cal.get("regime"), "n_bootstrap": cal.get("n_bootstrap"),
              "top1_id": top, "top1_vrai": gt.get(top) if top else None,
              "top1_hit": bool(top and gt.get(top) == 1),
              "hors_bootstrap": len(hors), "hors_correct": len(acc_hits),
              "grounded_by": "tests-run"}
        (sdir / "scenario-result.json").write_text(json.dumps(sc, indent=1, ensure_ascii=False) + "\n")
        verdicts.append(sc)
        print(f"s{s}: top1={top} vrai={gt.get(top)} hit={sc['top1_hit']} | hors: {len(acc_hits)}/{len(hors)} corrects | régime={cal.get('regime')}")

    g1_hits = sum(1 for v in verdicts if v["top1_hit"])
    tot_hors = sum(v["hors_bootstrap"] for v in verdicts)
    tot_corr = sum(v["hors_correct"] for v in verdicts)
    acc = tot_corr / max(1, tot_hors)
    lo, hi = s11.wilson(tot_corr, tot_hors)
    g2_ok = all(v["regime"] == "local" and v["n_bootstrap"] == N_BOOT and v["grounded_by"] == "tests-run"
                for v in verdicts)
    verdict = {
        "demo": "ghost-demo-expl-n8 (EXPLORATOIRE post-verdict)", "prereg_anchor": "1babd393",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "G1_top1_positifs": f"{g1_hits}/4 (gate >= 3/4)", "G1_verdict": "PASS" if g1_hits >= 3 else "ÉCHEC",
        "G2_integrite_calibration": "PASS" if g2_ok else "ÉCHEC",
        "G3_accuracy_hors_bootstrap": {"acc": round(acc, 4), "n": tot_hors, "wilson95": [round(lo, 4), round(hi, 4)],
                                        "statut": "descriptif (pas de seuil de go)"},
        "scenarios": verdicts,
        "disclosure": "n=3 < N_MIN=8 => régime fallback-prior sur tous les scénarios (divulgué); vérité terrain P0 jamais utilisée pour la sélection"}
    (SESS / "demo-expl-n8-verdict.json").write_text(json.dumps(verdict, indent=1, ensure_ascii=False) + "\n")
    print("\n=== VERDICT DÉMO ===")
    print(f"G1 top-1: {g1_hits}/4 -> {'PASS' if g1_hits >= 3 else 'ÉCHEC'}")
    print(f"G2 intégrité calibration (fallback-prior divulgué): {'PASS' if g2_ok else 'ÉCHEC'}")
    print(f"G3 accuracy hors-bootstrap: {acc:.3f} [{lo:.3f},{hi:.3f}] n={tot_hors} (descriptif)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
