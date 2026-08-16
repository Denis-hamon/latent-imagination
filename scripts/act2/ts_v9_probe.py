#!/usr/bin/env python3
"""Window coverage-ts-v9 — SONDE PRÉ-GEL A/B : lite.triple_coordinated +
affinity.triple_coordinated x (Flash x1, épinglé x1) = 4 appels max.
Règle gelée par (auteur, tâche) : >=1 diff applicable => bras validé ;
0 => exclusion de l'auteur pour cette tâche (disclosure).
Run: uv run python scripts/act2/ts_v9_probe.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARMS = {"flash": ("coverage-ts-9-flash", "DeepSeek-V4-Flash"),
        "pinned": ("coverage-ts-9-pinned", None)}  # None = GENFAM_MODEL par défaut
PROBE_TASKS = ["omniroute__lite.triple_coordinated",
               "omniroute__affinity.triple_coordinated"]

spec = importlib.util.spec_from_file_location("gg", ROOT / "scripts" / "act2" / "genfam_gen.py")
gg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gg)
spec2 = importlib.util.spec_from_file_location("pr2", ROOT / "scripts" / "act2" / "pilot_run.py")
pr = importlib.util.module_from_spec(spec2)
sys.modules["pilot_run"] = pr
spec2.loader.exec_module(pr)
MODEL_OVERRIDE = {"m": gg.MODEL}


def call_t07_model(prompt: str) -> dict:
    import subprocess
    key = os.environ.get("LI_GALERE_KEY") or os.environ.get("OPENCODE_GALERE_KEY")
    body = json.dumps({"model": MODEL_OVERRIDE["m"],
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.7,
                       "max_tokens": int(os.environ.get("PILOT_MAX_TOKENS", "16000"))})
    cmd = ["curl", "-sS", "--max-time", "580", "-X", "POST", pr.GALERE,
           "-H", "Content-Type: application/json",
           "-H", "User-Agent: opencode/1.0", "--data-binary", "@-"]
    if key:
        cmd += ["-H", f"Authorization: Bearer {key}"]
    p = subprocess.run(cmd, input=body.encode(), capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"curl rc={p.returncode}: {p.stderr[-300:].decode()}")
    j = json.loads(p.stdout.decode())
    if "choices" not in j:
        raise RuntimeError(f"payload: {str(j)[:300]}")
    mm = j["choices"][0]["message"]
    return {"text": (mm.get("content") or "") + "\n" + (mm.get("reasoning") or mm.get("reasoning_content") or ""),
            "usage": j.get("usage", {})}


pr.call_model = call_t07_model


def main() -> int:
    verdicts = {}
    for arm, (cdir, model) in ARMS.items():
        MODEL_OVERRIDE["m"] = model or gg.MODEL
        Q = ROOT / "data/landing/act2-pilot" / cdir
        os.environ["PILOT_CAMPAIGN_DIR"] = cdir
        pr.os.environ["PILOT_CAMPAIGN_DIR"] = cdir
        log = Q / "call-log.jsonl"
        staging = json.loads((Q / "staging-extract.json").read_text())
        by_id = {t["instance_id"]: t for t in staging["tasks"]}
        for tid in PROBE_TASKS:
            t = by_id[tid]
            buggy = (Q / f"{tid.replace('/', '_')}.buggy.py").read_text()
            task = {"instance_id": tid, "problem": t["problem"],
                    "f2p": t["f2p"][:6], "target": t["target"]}
            try:
                g = pr.gen_patch(task)
                err = None
            except Exception as e:  # noqa: BLE001
                g, err = None, str(e)[:300]
            row = {"ts": datetime.now(UTC).isoformat(), "window": "coverage-ts-v9",
                   "stage": "probe-arm", "slot": f"{tid}-probe-{arm}",
                   "model": MODEL_OVERRIDE["m"], "campaign": cdir, "temperature": 0.7}
            got = False
            if err:
                row["error"] = err
            else:
                row.update({"prompt_sha256": g["prompt_sha256"], "reply_sha256": g["reply_sha256"],
                            "raw_reply": g["raw_reply"], "usage": g["usage"]})
                san = pr.extract_diff_sanitized(g["raw_reply"])
                diff = mode = None
                if san:
                    diff, _ = pr.apply_and_export_debug(buggy, san + "\n", t["target"])
                    mode = "strict-git" if diff else None
                    if diff is None:
                        diff, _ = gg.apply_fuzz_reexport(buggy, san + "\n", t["target"])
                        mode = "fuzz-reexport" if diff else None
                got = diff is not None
                row.update({"diff_mode": mode,
                            "diff_sha256": sha256(diff.encode()).hexdigest() if diff else None})
            with log.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            key = f"{arm}:{tid}"
            verdicts[key] = "diff applicable" if got else f"NO-DIFF{' (err)' if err else ''}"
            print(f"{arm:7} {tid[-38:]}: {verdicts[key]}", flush=True)
    out = ROOT / "data/landing/act2-pilot" / "ts-v9" / "probe-v9-verdict.json"
    out.write_text(json.dumps({"window": "coverage-ts-v9",
                               "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                               "rule": ">=1 diff applicable par (auteur,tâche) sinon exclusion",
                               "verdicts": verdicts}, indent=1) + "\n")
    for k, v in verdicts.items():
        print(k, "=>", v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
