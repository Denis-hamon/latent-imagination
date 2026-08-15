#!/usr/bin/env python3
"""MCP flywheel — stage 1 : collecte des paires groundées depuis mcp-log.jsonl.

Le MCP (ghost_server (GHOST MCP) v0.3+) journalise chaque risk_scan (state, diff,
reporter=LLM auteur, score, décision) et chaque report_outcome (call_id,
passed, reporter, grounded_by). Ce script apparie les deux et produit le
matériau du renforcement du world model :

  1. join outcome ↔ risk_scan par call_id ;
  2. filtre : issue GROUNDÉE seulement (grounded_by renseigné — leçon S11/S13 :
     jamais de label auto-déclaré par le LLM) ;
  3. dédup : par diff_sha contre le batch ET contre les diffs du pool courant
     (les régénérations identiques n'apportent rien — mesuré en S12 : 16/23) ;
  4. stratification par reporter (auteur) : n, taux de positifs, taux d'abstention
     du serveur sur ses diffs — alerte poison si un auteur s'écarte trop de la
     base (leçon S11 : auteur hétérogène = risque de géométrie empoisonnée).

Sorties : mcp-flywheel/candidates.json (les paires prêtes à embed/promouvoir)
        + mcp-flywheel/collect-report.json. Zéro embed, zéro promotion : la
géométrie v9 et l'entrée au pool restent des étapes distinctes, à la main de
l'owner (comme les pools v6/v7/v8).
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
LOG = PILOT / "mcp-log.jsonl"
OUT = PILOT / "mcp-flywheel"
POOL_JSON = PILOT / "latent-pool-v8.json"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not LOG.is_file():
        print("mcp-log.jsonl absent — aucun trafic MCP encore.")
        return 0
    scans: dict[str, dict] = {}
    outcomes: dict[str, dict] = {}
    n_other = 0
    for ln in LOG.read_text().splitlines():
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if e.get("type") == "risk_scan" and e.get("state_text"):
            scans[e["call_id"]] = e
        elif e.get("type") == "outcome":
            outcomes[e["call_id"]] = e
        else:
            n_other += 1

    pool = json.loads(POOL_JSON.read_text()) if POOL_JSON.is_file() else []
    known_diffs = {sha256(r["diff"].strip().encode()).hexdigest() for r in pool}
    pos_rate_pool = sum(r["y"] for r in pool) / max(1, len(pool))

    pairs, seen = [], set()
    stats = defaultdict(lambda: {"n": 0, "pos": 0, "abstained": 0, "dups": 0})
    ungrounded = unmatched = 0
    for cid, o in outcomes.items():
        s = scans.get(cid)
        if not s:
            unmatched += 1
            continue
        rep = o.get("reporter") or s.get("reporter") or "unknown"
        st = stats[rep]
        st["n"] += 1
        if not o.get("grounded_by"):
            ungrounded += 1
            continue  # leçon S11 : pas de label auto-déclaré dans le pool
        h = s.get("diff_sha") or sha256(s["diff_text"].strip().encode()).hexdigest()
        st["pos"] += int(bool(o["passed"]))
        st["abstained"] += int(s.get("decision") == "abstain")
        if h in known_diffs or h in seen:
            st["dups"] += 1
            continue
        seen.add(h)
        pairs.append({
            "call_id": cid, "reporter": rep,
            "grounded_by": o["grounded_by"], "passed": bool(o["passed"]),
            "state_text": s["state_text"], "diff_text": s["diff_text"],
            "state_sha": s.get("state_sha"), "diff_sha": h,
            "server_decision": s.get("decision"),
            "server_confidence": s.get("confidence"),
            "exclude_task": s.get("exclude_task"),
            "collected_at": o["ts"],
        })

    alerts = []
    for rep, st in stats.items():
        if st["n"] >= 10:
            pr = st["pos"] / st["n"]
            if abs(pr - pos_rate_pool) > 0.35:
                alerts.append(f"auteur {rep}: taux positifs {pr:.0%} vs base pool "
                              f"{pos_rate_pool:.0%} — vérif distribution avant merge "
                              f"(leçon S11)")
    # pairs sans identité d'auteur : visibles, jamais silencieusement perdus
    n_reporter_missing = sum(1 for s in scans.values()
                             if s.get("reporter_missing") or not s.get("reporter"))
    report = {
        "log": str(LOG),
        "risk_scan_avec_capture": len(scans),
        "scans_sans_reporter": n_reporter_missing,
        "outcomes": len(outcomes),
        "outcomes_non_appariés": unmatched,
        "outcomes_non_groundés_rejetés": ungrounded,
        "paires_promouvables": len(pairs),
        "pool_courant": {"lignes": len(pool), "taux_positifs": round(pos_rate_pool, 3)},
        "par_auteur": {k: dict(v) for k, v in sorted(stats.items())},
        "alertes_poison": alerts,
        "autres_entrées_log": n_other,
    }
    (OUT / "candidates.json").write_text(json.dumps(pairs, indent=1))
    (OUT / "collect-report.json").write_text(json.dumps(report, indent=1))
    _history_snapshot("collect-report.json")
    print(json.dumps(report, indent=1))
    print(f"\n→ {OUT / 'candidates.json'} ({len(pairs)} paires prêtes pour "
          f"assemble (stage 2) — embed/serve restent des étapes node-serveur)")
    return 0


# ---------------------------------------------------------------------------
# Stage 2 (story GHOST-next #4): assemble -> promote-report
# ---------------------------------------------------------------------------
# Honnêteté de conception : les paires issues du log MCP sont GOAL-FREE (state
# + diff + issue groundée, mais PAS de gold / diff de référence). Elles
# alimentent donc l'axe géométrique déjà servi par risk_scan (cd = E_s + E_d,
# attracteur goal-free) et sont EXCLUES de l'axe gold (cg = E_s + E_g). Le
# champ E_goal d'une ligne goal-free n'est pas inventé : la ligne porte
# goal_free=true et le promote/eval n'utilisent que cd. L'embed réel et le
# serve du NPZ restent des étapes node-serveur (GPU), divulguées, jamais
# simulées ici.

STAGE2_ROWS = OUT / "flywheel-rows.json"
STAGE2_REPORT = OUT / "promote-report.json"
V9_JSON = PILOT / "latent-pool-v9.json"
V9_NPZ = PILOT / "latent-pool-v9.npz"
V9_CALIB = ROOT / "governance" / "act2" / "arm-artifacts" / "risk-scan-v9-calibration.json"

# Journal de tentatives (story 9.2, discipline R4) : CHAQUE invocation laisse
# une ligne — un crash se lit comme une interruption dans l'historique,
# jamais comme un succès continu ininterrompu.
RUNS_LOG = OUT / "runs.log"
HISTORY = OUT / "history"


def _journal(stage: str, exit_code: int, counts: dict) -> None:
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        with RUNS_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 "stage": stage, "exit": exit_code, **counts},
                                sort_keys=True) + "\n")
    except OSError:
        print(f"[journal] impossible d'écrire {RUNS_LOG} — trace de tentative perdue",
              file=sys.stderr)


def _history_snapshot(name: str) -> None:
    """Copie datée d'audit (le fichier live reste l'état courant lisible machine)."""
    try:
        HISTORY.mkdir(parents=True, exist_ok=True)
        src = OUT / name
        if src.is_file():
            stamp = time.strftime("%Y%m%dT%H%M%SZ")
            dst = HISTORY / f"{name.replace('.json', '')}-{stamp}.json"
            if not dst.exists():
                dst.write_text(src.read_text())
    except OSError as exc:
        print(f"[history] snapshot ignoré ({type(exc).__name__})", file=sys.stderr)


def assemble() -> int:
    """candidates.json -> flywheel-rows.json : label gate (grounded seul),
    dédup contre le pool courant, provenance gardée, flag goal_free=true."""
    if not (OUT / "candidates.json").is_file():
        print("candidates.json absent — lancer d'abord le stage 1 (collect).")
        return 0
    cands = json.loads((OUT / "candidates.json").read_text())
    pool = json.loads(POOL_JSON.read_text()) if POOL_JSON.is_file() else []
    known_diffs = {sha256(r["diff"].strip().encode()).hexdigest() for r in pool}
    rows, seen, rejected = [], set(), {"not_grounded": 0, "dup_pool": 0, "dup_batch": 0}
    for c in cands:
        if not c.get("grounded_by"):
            rejected["not_grounded"] += 1
            continue
        h = c.get("diff_sha") or sha256(c["diff_text"].strip().encode()).hexdigest()
        if h in known_diffs:
            rejected["dup_pool"] += 1
            continue
        if h in seen:
            rejected["dup_batch"] += 1
            continue
        seen.add(h)
        rows.append({
            # pas de task id natif : identité = diff_sha (content-addressed, AD-12)
            "task": f"flywheel:{h[:16]}",
            "arm": "flywheel",
            "campaign": "mcp-flywheel-1",
            "state": c["state_text"],
            "goal_free": True,          # pas de gold — axe cd seulement
            "diff": c["diff_text"],
            "y": 1 if c["passed"] else 0,  # label = issue groundée par exécution
            "provenance": {
                "call_id": c["call_id"], "reporter": c.get("reporter", "unknown"),
                "grounded_by": c["grounded_by"],
                "server_decision": c.get("server_decision"),
                "diff_sha256": h,
                "collected_at": c.get("collected_at"),
            },
        })
    (STAGE2_ROWS).write_text(json.dumps(rows, indent=1))
    summary = {"candidates_in": len(cands), "rows_out": len(rows), "rejected": rejected,
               "positives": sum(r["y"] for r in rows),
               "all_goal_free": all(r.get("goal_free") for r in rows)}
    (OUT / "assemble-report.json").write_text(json.dumps(summary, indent=1))
    _history_snapshot("assemble-report.json")
    print(json.dumps(summary, indent=1))
    print(f"\n→ {STAGE2_ROWS} ({len(rows)} lignes goal-free prêtes pour embed node-serveur)")
    return 0


def promote_report() -> int:
    """Génère le rapport de promotion v8->v9 et la calibration cible, SANS
    toucher au NPZ ni au service. Si les lignes assemblées ne sont pas encore
    embeddées (NPZ v9 absent), divulgue 'embed pending on node' au lieu de
    feindre la géométrie. Aucune écriture de serving ici : l'owner swap sur le
    node après embed."""
    if not STAGE2_ROWS.is_file():
        print("flywheel-rows.json absent — lancer --stage assemble.")
        return 0
    rows = json.loads(STAGE2_ROWS.read_text())
    base = json.loads(POOL_JSON.read_text()) if POOL_JSON.is_file() else []
    # thr cible = médiane du F1 goal-free LOAO sur le pool fusionné (recette v8 :
    # thr = médiane pool du score f1=d_fail-d_pass, conf=|score-thr|). Le npz
    # v9 n'existant pas avant l'embed node-serveur, on ne peut PAS recalculer le
    # régime ici sans les embeddings -> divulgation honnête.
    v9_npz = V9_NPZ
    embed_done = v9_npz.is_file()
    rep = {
        "v8": {"rows": len(base),
               "sha256_pool_json": sha256(POOL_JSON.read_bytes()).hexdigest() if POOL_JSON.is_file() else None},
        "flywheel_rows": len(rows),
        "positives_added": sum(r["y"] for r in rows),
        "v9_target_json": str(V9_JSON),
        "v9_npz_present": embed_done,
        "status": ("ready-to-serve (embed fait; owner: swap LI_POOL_JSON/LI_POOL_NPZ "
                   "sur le node, recalibrer tau, restart ghost-mcp)"
                   if embed_done else
                   "EMBED PENDING ON NODE — les lignes sont assemblées mais la géométrie "
                   "v9 n'existe pas encore ; lancer l'embed GPU (recette embed_pool, "
                   "E_goal omis car goal_free) avant tout swap de serving. Aucune "
                   "calibration ni serving n'est produit tant que le NPZ v9 est absent."),
        "rollback": ("Le serving est resté sur v8 tant que LI_POOL_JSON/LI_POOL_NPZ ne "
                     "sont pas re-pointés; rollback = re-pointer vers v8 + restart."),
        "goal_free_note": "toutes les lignes flywheel sont goal_free=true ; l'axe gold "
                          "(cg/assess) ne doit pas les consommer.",
    }
    (STAGE2_REPORT).write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    return 0


def _report_counts(name: str, keys: tuple[str, ...]) -> dict:
    try:
        doc = json.loads((OUT / name).read_text())
        return {k: doc.get(k) for k in keys if k in doc}
    except (OSError, ValueError):
        return {}


def _dispatch(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="MCP flywheel (stage 1 collect / stage 2 assemble|promote-report)")
    ap.add_argument("log", nargs="?", default=None, help="path to mcp-log.jsonl (stage 1)")
    ap.add_argument("--stage", choices=["collect", "assemble", "promote-report"], default="collect")
    a = ap.parse_args(argv)
    global LOG
    if a.stage == "collect":
        if a.log:
            LOG = Path(a.log)
        rc = main()
        _journal("collect", rc, _report_counts(
            "collect-report.json", ("risk_scan_avec_capture", "scans_sans_reporter",
                                    "paires_promouvables", "outcomes_non_groundés_rejetés")))
        return rc
    if a.stage == "assemble":
        rc = assemble()
        _journal("assemble", rc, _report_counts(
            "assemble-report.json", ("candidates_in", "rows_out")))
        return rc
    rc = promote_report()
    _journal("promote-report", rc, {})
    return rc


if __name__ == "__main__":
    raise SystemExit(_dispatch(sys.argv[1:]))
