"""THE canonical Act II delta pipeline — stdlib-only, commodity hardware (Tier-1
replay). THIS module is the one true implementation the replay bundles carry;
`harness/delta.py` (package side) is pinned equivalent by a shared-fixture
equivalence test, which is the anti-drift tripwire.

Reads: slice/{act1.json, act2.json, decision.toml, design.toml}
Writes: out/delta.json — the FULL claim line (ERBVE + exec-per-task + ttv with
disclosed coverage), per-series rows, OQ-4 verdict, citations.
Guards: exact paired series sets, unique keys, finite rates, n_tasks>0,
sealed values finite+positive; any breach → exit 3 with a jsonl error line.
"""

from __future__ import annotations

import json
import math
import sys
import tomllib
from pathlib import Path
from typing import NoReturn

REQ = ("family", "generation", "macro_rate", "total_attempts", "n_tasks")
# the ONLY home of these claim-line literals (the package delta.py imports them —
# one text, two runtimes, zero drift)
CI_STATUS = ("uncomputable from aggregated points — raw-attempt bootstrap lives in the "
             "replay tier")
AGGREGATION_NOTE = "pooled macro-per-task, Act I discipline (never a mean of family means)"
INCLUSIVITY_NOTE = "inclusive (sealed); comparison at full precision, display rounded"


def _die(msg: str, **ctx) -> NoReturn:
    print(json.dumps({"error": msg, "ctx": ctx}, sort_keys=True), file=sys.stderr)
    raise SystemExit(3)


def _load_sealed(root: Path, name: str, table: list[str]) -> float:
    p = root / "slice" / name
    if not p.is_file():
        _die("sealed file missing", file=name)
    try:
        data = tomllib.loads(p.read_bytes().decode("utf-8"))
        node = data
        for t in table:
            node = node[t]
        v = float(node)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, KeyError, TypeError, ValueError):
        _die("sealed value unreadable", file=name)
    if not math.isfinite(v) or v <= 0:
        _die("sealed value not finite-positive", file=name)
    return v


def _points(root: Path, name: str) -> list[dict]:
    p = root / "slice" / name
    if not p.is_file():
        _die("points file missing", file=name)
    rows = json.loads(p.read_text(encoding="utf-8"))["points"]
    seen = set()
    for r in rows:
        for f in REQ:
            if f not in r:
                _die("point missing field", file=name, field=f)
        k = (r["family"], r["generation"])
        if k in seen:
            _die("duplicate series key", file=name, key=list(k))
        seen.add(k)
        mr = r["macro_rate"]
        if not isinstance(mr, (int, float)) or isinstance(mr, bool) or not math.isfinite(mr):
            _die("macro_rate invalid", file=name, key=list(k))
        if not isinstance(r["n_tasks"], int) or isinstance(r["n_tasks"], bool) or r["n_tasks"] <= 0:
            _die("n_tasks invalid", file=name, key=list(k))
    return rows


def _pooled(rows: list[dict]) -> float:
    return sum(r["macro_rate"] * r["n_tasks"] for r in rows) / sum(r["n_tasks"] for r in rows)


def _exec(rows: list[dict]) -> float:
    return sum(r["total_attempts"] for r in rows) / sum(r["n_tasks"] for r in rows)


def compute(root: Path) -> dict:
    a1, a2 = _points(root, "act1.json"), _points(root, "act2.json")
    if not a2:
        _die("no Act II points")
    k1 = {(r["family"], r["generation"]) for r in a1}
    k2 = {(r["family"], r["generation"]) for r in a2}
    if k1 != k2:
        _die("series sets differ", only1=sorted(map(str, k1 - k2)), only2=sorted(map(str, k2 - k1)))
    m1, m2 = _pooled(a1), _pooled(a2)
    mp = _load_sealed(root, "decision.toml", ["publishable_delta", "minimum_publishable_pp"])
    tol = _load_sealed(root, "design.toml", ["tolerances", "replay_t2_pp"])
    from hashlib import sha256

    cites = {
        "decision_toml_sha256": sha256((root / "slice" / "decision.toml").read_bytes()).hexdigest(),
        "design_toml_sha256": sha256((root / "slice" / "design.toml").read_bytes()).hexdigest(),
    }
    d_pp = (m1 - m2) * 100.0

    ttv_pooled = None
    keyed1 = {(r["family"], r["generation"]): r for r in a1}
    keyed2 = {(r["family"], r["generation"]): r for r in a2}
    have = [k for k in keyed2 if "mean_time_to_valid_s" in keyed1[k] and "mean_time_to_valid_s" in keyed2[k]]
    if len(have) == len(k2) and k2:
        n = sum(keyed1[k]["n_tasks"] for k in have)
        ttv_pooled = (sum(keyed2[k]["mean_time_to_valid_s"] * keyed2[k]["n_tasks"] for k in have)
                      - sum(keyed1[k]["mean_time_to_valid_s"] * keyed1[k]["n_tasks"] for k in have)) / n

    return {
        "claim_line": {
            "erbve_delta_pp": d_pp,
            "exec_per_task_delta": _exec(a2) - _exec(a1),
            "time_to_valid_delta_s": ttv_pooled,
            "ttv_coverage": f"{len(have)}/{len(k2)} paired series",
            "aggregation": AGGREGATION_NOTE,
            "delta_ci": None,
            "ci_status": CI_STATUS,
        },
        "per_series": [
            {
                "family": k[0], "generation": k[1],
                "erbve_delta_pp": (keyed1[k]["macro_rate"] - keyed2[k]["macro_rate"]) * 100.0,
                "act1_macro": keyed1[k]["macro_rate"],
                "act2_macro": keyed2[k]["macro_rate"],
                "exec_delta_per_task": (keyed2[k]["total_attempts"] / keyed2[k]["n_tasks"])
                - (keyed1[k]["total_attempts"] / keyed1[k]["n_tasks"]),
                "n_tasks": keyed2[k]["n_tasks"],
                **({"ttv_delta_s": keyed2[k]["mean_time_to_valid_s"] - keyed1[k]["mean_time_to_valid_s"]}
                   if k in have else {}),
            }
            for k in sorted(k2)
        ],
        "oq4": {"minimum_publishable_pp": mp, "met": d_pp >= mp,
                 "verdict": "material-reduction" if d_pp >= mp else "below-threshold",
                 "inclusivity": INCLUSIVITY_NOTE},
        "tolerance_pp": tol,
        "_citations": cites,
    }


def main() -> int:
    if "--root" not in sys.argv or sys.argv.index("--root") + 1 >= len(sys.argv):
        _die("usage: run.py --root <bundle>")
    root = Path(sys.argv[sys.argv.index("--root") + 1]).resolve()
    d = compute(root)
    out = root / "out" / "delta.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes((json.dumps(d, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
