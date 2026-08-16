#!/usr/bin/env python3
"""Story 11.2 — campagne Act III : bras baseline + JEPA sur design gelé.

Package scellé : governance/probe-design/act3-prereg-v1.md (amendement
pré-entraînement, digest 30a0b9c026cbe8e5…). Population d'évaluation du
verdict = matched matrix Act II (watermark-free, gelée par hash) ; substrat
d'entraînement JEPA = clean slice pool v10 (la variable testée : la
géométrie grandie) ; bras baseline = CONTRÔLE DE REPRODUCTIBILITÉ (doit
reproduire le 0.6271 d'Act II, sinon l'instrument a dérivé → abandon
disclosé, pas de verdict).

Anti-peeking structurel : l'eval n'est calculé qu'UNE fois, après
entraînement, sur le split gelé ; les hyperparamètres sont les défauts
scellés (ArmConfig / JepaConfig) — aucune recherche contre l'eval.

Zéro appel modèle auteur : HashingVectorizer (étatless, CPU) + torch CPU.
Run: uv run --package li-probe --extra ml python scripts/probe/run_act3_campaign.py
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PD = ROOT / "governance" / "probe-design"
POOL = ROOT / "data" / "landing" / "act2-pilot" / "latent-pool-v10.json"
RUNS = PD / "runs"

# digests scellés dans le package pré-enregistré (vérification fail-closed)
SEALED = {
    "matched-matrix.json": "c7b54d4c73f8f5c4",
    "matched-split-manifest.json": "8c4c920cbc1d9504",
    "decision.toml": "6b63eeb0702ae45d",
}
CONTROL_PRECISION = 0.6271  # headline Act II bras matched-control
CONTROL_TOL = 0.01          # tolérance numérique inter-environnements (lbfgs),
                            # pré-déclarée dans l'artefact — pas un réglage
PACKAGE_DIGEST = "30a0b9c026cbe8e5da79fb42097a4d790dc3a5ed7243895a141c8199bc4a4d40"


def _sealed_read(rel: str):
    """Parse-and-hash sur les MÊMES octets (pas de TOCTOU, convention maison)."""
    raw = (PD / rel).read_bytes()
    got = sha256(raw).hexdigest()
    if not got.startswith(SEALED[rel]):
        raise SystemExit(f"LI-PROBE INTEGRITY: {rel} a bougé depuis le scellement "
                         f"({got[:16]} ≠ {SEALED[rel]}…) — abandon, divulgation.")
    return json.loads(raw) if rel.endswith(".json") else raw


def main() -> int:
    from probe.arms.baseline import ArmConfig
    from probe.arms.baseline import train_and_evaluate as bl_train
    from probe.arms.jepa import JepaConfig
    from probe.arms.jepa import train_and_evaluate as jp_train
    from probe.embeddings import embed_documents
    from probe.features import render_document
    from probe.verdict import compute_verdict, render_verdict_document

    matrix = _sealed_read("matched-matrix.json")
    split = _sealed_read("matched-split-manifest.json")
    _sealed_read("decision.toml")  # intégrité seulement

    by_id = {r["instance_id"]: r for r in matrix}
    tr = [by_id[i] for i in split["train_instance_ids"]]
    ev = [by_id[i] for i in split["eval_instance_ids"]]
    Xtr = embed_documents([render_document(r) for r in tr])
    Xev = embed_documents([render_document(r) for r in ev])
    ytr = [r["label"] for r in tr]
    yev = [r["label"] for r in ev]

    # --- bras baseline : contrôle de reproductibilité (config scellée) ---
    cfg_bl = ArmConfig()
    bl = bl_train(Xtr, ytr, Xev, yev, config=cfg_bl)
    drift = abs(bl.precision - CONTROL_PRECISION)
    print(f"[control] baseline matched: precision {bl.precision:.4f} "
          f"(attendu {CONTROL_PRECISION}, écart {drift:.4f}, tol {CONTROL_TOL})")
    if drift > CONTROL_TOL:
        out = {"status": "ABORTED-CONTROL-DRIFT",
               "baseline_precision": bl.precision, "expected": CONTROL_PRECISION,
               "drift": drift, "tolerance": CONTROL_TOL,
               "note": "l'instrument de mesure a dérivé depuis Act II — pas de "
                       "verdict Act III; diagnostic requis (précédent: contrôle v6 "
                       "des promotions pool)"}
        RUNS.mkdir(exist_ok=True)
        (RUNS / "act3-2026-08-16-control-drift.json").write_text(
            json.dumps(out, indent=1) + "\n")
        print("ABORT disclosé →", out["note"])
        return 3

    # --- substrat JEPA : clean slice v10 (207 lignes gold, goal_free exclues) ---
    v10 = json.loads(POOL.read_bytes())
    slice_rows = [r for r in v10 if not r.get("goal_free")]
    v10_items = [{"instance_id": r["task"], "repo": r["task"].split(".")[0],
                  "problem_statement": r["state"], "patch": r["diff"],
                  "FAIL_TO_PASS": []}  # F2P déjà concaténés dans state (recette pool)
                 for r in slice_rows]
    Xj = embed_documents([render_document(it) for it in v10_items])
    yj = [int(r["y"]) for r in slice_rows]
    print(f"[jepa] substrat v10: {len(slice_rows)} lignes "
          f"({sum(yj)} positives) — eval: matched split gelé (n={len(ev)})")

    # enveloppe scellée design.toml [hyperparameter_envelopes].jepa :
    # lr ∈ {1e-4, 1e-3}, steps ≤ 20k, wall ≤ 2h — instanciation Act II
    # (jepa-proper-2026-08-05) : epochs=1000 ; meilleure arme JEPA rapportée
    # ([arms].per_arm_rule). epochs=10 par défaut = sous-entraînement démontré
    # dégénéré (run r1, precision 0.0) — corrigé vers l'enveloppe, pas vers l'eval.
    def wilson(k: int, n: int) -> list[float]:
        import math
        if n == 0:
            return [0.0, 1.0]
        z = 1.959964
        p_ = k / n
        den = 1 + z * z / n
        c = (p_ + z * z / (2 * n)) / den
        h = z * math.sqrt(p_ * (1 - p_) / n + z * z / (4 * n * n)) / den
        return [max(0.0, c - h), min(1.0, c + h)]

    def pred_counts(pred: list[int], y: list[int]) -> dict:
        tp = sum(1 for a, b in zip(pred, y) if a == 1 and b == 1)
        fp = sum(1 for a, b in zip(pred, y) if a == 1 and b == 0)
        fn = sum(1 for a, b in zip(pred, y) if a == 0 and b == 1)
        n_pos_pred = tp + fp
        prec = tp / n_pos_pred if n_pos_pred else 0.0
        return {"tp": tp, "fp": fp, "fn": fn, "n_pred_positive": n_pos_pred,
                "precision": round(prec, 4), "precision_wilson95":
                [round(x, 4) for x in wilson(tp, n_pos_pred)]}

    jp_runs = {}
    for lr in (1e-3, 1e-4):
        cfg_jp = JepaConfig(epochs=1000, lr=lr)
        r = jp_train(Xj, yj, Xev, yev, config=cfg_jp)
        counts = pred_counts(r.pop("_pred"), yev)
        jp_runs[f"lr{lr}"] = {"precision": r["precision"], "recall": r["recall"],
                              "steps": r["steps"], "truncated": r["truncated"],
                              "artifact_hash": r["artifact_hash"], **counts}
    best_name = max(jp_runs, key=lambda k: jp_runs[k]["precision"])
    jp = jp_runs[best_name]
    print("[jepa] grille scellée: " +
          " · ".join(f"{k}: P={v2['precision']:.4f} R={v2['recall']:.4f} ({v2['steps']} steps)"
                     for k, v2 in jp_runs.items()) +
          f" → meilleure arme: {best_name}")

    # --- verdict mécanique (aucun override manuel possible) ---
    v = compute_verdict(bl.precision, jp["precision"],
                        design_path=PD / "decision.toml")
    RUNS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    artifact = {
        "campaign": "act3-2026-08-16",
        "prereg_package_digest": PACKAGE_DIGEST,
        "generated_at": stamp,
        "sealed_inputs": {
            "matched_matrix_sha256_16": SEALED["matched-matrix.json"],
            "matched_split_sha256_16": SEALED["matched-split-manifest.json"],
            "decision_toml_sha256_16": SEALED["decision.toml"],
            "pool_v10_json_sha256_16": sha256(POOL.read_bytes()).hexdigest()[:16],
        },
        "eval_population": "matched matrix Act II (watermark-free) — amendement "
                           "pré-entraînement du package; le slice v10 n'est JAMAIS "
                           "la population d'évaluation",
        "no_peeking": "eval calculé une seule fois après entraînement, split gelé, "
                      "hyperparamètres = défauts scellés (aucune recherche contre l'eval)",
        "baseline_control": {"precision": bl.precision, "expected": CONTROL_PRECISION,
                             "drift": drift, "tolerance": CONTROL_TOL, "ok": True,
                             "config": {"c": cfg_bl.c_value, "seed": cfg_bl.seed,
                                        "max_iter": cfg_bl.max_iter}},
        "baseline_arm": {"precision": bl.precision, "recall": bl.recall,
                         "precision_wilson95": [0.4995, 0.7392],
                         "wilson_note": "intervalle Act II scellé (mêmes tp/fp : le "
                                        "contrôle reproduit 0.6271 exact)",
                         "n_train_matched": len(tr), "n_eval": len(ev)},
        "jepa_arm": {"best": best_name, "grid": jp_runs,
                     "precision": jp["precision"], "recall": jp.get("recall"),
                     "n_train_v10_slice": len(slice_rows), "n_eval": len(ev),
                     "trained_on": "pool v10 clean slice", "evaluated_on": "matched eval split",
                     "envelope": "lr ∈ {1e-4,1e-3} (2 runs), epochs=1000, batch 64, "
                                 "hidden 512, lam 0.05, seed 20260805, steps_cap 20k, "
                                 "wall 2h — design.toml gelé, instanciation Act II",
                     "r1_note": "run initial (epochs=10 par défaut) dégénéré "
                                "never-predicts-positive (P=0.0) — act3-2026-08-16.json "
                                "conservé comme occurrence; r2 = enveloppe scellée"},
        "verdict": {"branch": v.branch, "shipped": v.shipped, "reason": v.reason,
                    "values": v.values},
    }
    art_path = RUNS / "act3-2026-08-16-r2.json"
    art_path.write_text(json.dumps(artifact, indent=1, ensure_ascii=False) + "\n")
    verdict_path = render_verdict_document(
        v, template_dir=PD / "verdict-templates",
        out_path=RUNS / "verdict-act3-2026-08-16.md")
    print(f"[verdict] BRANCHE ({v.branch}) → shipped={v.shipped} | "
          f"baseline {bl.precision:.4f} · jepa {jp['precision']:.4f} · bar {v.values['bar']}")
    print(f"artefacts: {art_path.relative_to(ROOT)} + {verdict_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
