#!/usr/bin/env python3
"""Window coverage-ts-v8 — SONDE PRÉ-GEL MULTI-AUTEURS : 1 tâche éprouvée
(zod single_max_inclusive) x 2 tirages x 3 auteurs = 6 appels max (cap 70).
Règle gelée : >=1 diff applicable/auteur => VALIDÉ ; 0/2 => auteur EXCLU.
Le wrapper appel conserve la forme s12 gelée (T=0.7, max_tokens 16000) ;
seul le model id change. Journal par campagne coverage-ts-8-<tag>.
Run: uv run python scripts/act2/ts_v8_probe.py
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
AUTHORS = {"flash": "DeepSeek-V4-Flash", "glm": "GLM-5.2-NVFP4",
           "qwen24t": "Qwen3.8-2.4T-A95B-NVFP4"}
PROBE_TASK = "zod__checks.single_max_inclusive"
spec = importlib.util.spec_from_file_location("gg", ROOT / "scripts" / "act2" / "genfam_gen.py")
gg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gg)
spec2 = importlib.util.spec_from_file_location("pr2", ROOT / "scripts" / "act2" / "pilot_run.py")
pr = importlib.util.module_from_spec(spec2)
sys.modules["pilot_run"] = pr
spec2.loader.exec_module(pr)
MODEL_OVERRIDE = {"m": gg.MODEL}


def call_t07_model(prompt: str) -> dict:
    """Forme identique à gg.call_t07 — seul le model id est paramétré."""
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
    quota = json.loads((ROOT / "data/landing/act2-pilot/ts-v7/quota-tasks.json").read_text())
    task = next(t for t in quota["tasks"] if t["instance_id"] == PROBE_TASK)
    verdicts = {}
    for tag, model in AUTHORS.items():
        MODEL_OVERRIDE["m"] = model
        cdir = f"coverage-ts-8-{tag}"
        Q = ROOT / "data/landing/act2-pilot" / cdir
        os.environ["PILOT_CAMPAIGN_DIR"] = cdir
        pr.os.environ["PILOT_CAMPAIGN_DIR"] = cdir
        log = Q / "call-log.jsonl"
        buggy = (Q / f"{PROBE_TASK.replace('/', '_')}.buggy.py").read_text()
        n_diff = 0
        for d in (1, 2):
            tdict = {"instance_id": PROBE_TASK, "problem": task["problem"],
                     "f2p": task["f2p"][:6], "target": task["target"]}
            try:
                g = pr.gen_patch(tdict)
                err = None
            except Exception as e:  # noqa: BLE001
                g, err = None, str(e)[:300]
            row = {"ts": datetime.now(UTC).isoformat(), "window": "coverage-ts-v8",
                   "stage": "author-probe", "slot": f"{PROBE_TASK}-d{d}",
                   "model": model, "campaign": cdir, "temperature": 0.7}
            if err:
                row["error"] = err
            else:
                row.update({"prompt_sha256": g["prompt_sha256"], "reply_sha256": g["reply_sha256"],
                            "raw_reply": g["raw_reply"], "usage": g["usage"]})
                san = pr.extract_diff_sanitized(g["raw_reply"])
                diff = mode = None
                if san:
                    diff, _ = pr.apply_and_export_debug(buggy, san + "\n", task["target"])
                    mode = "strict-git" if diff else None
                    if diff is None:
                        diff, _ = gg.apply_fuzz_reexport(buggy, san + "\n", task["target"])
                        mode = "fuzz-reexport" if diff else None
                row.update({"diff_mode": mode,
                            "diff_sha256": sha256(diff.encode()).hexdigest() if diff else None})
            with log.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            got = bool(row.get("diff_sha256"))
            n_diff += got
            print(f"{tag} d{d}: {'diff (' + row['diff_mode'] + ')' if got else 'no-diff' + (' ERR' if err else '')}", flush=True)
        verdicts[model] = "VALIDÉ" if n_diff >= 1 else "EXCLU (0/2, règle gelée)"
    (ROOT / "data/landing/act2-pilot/ts-v7" / "probe-v8-verdict.json").write_text(
        json.dumps({"window": "coverage-ts-v8", "task": PROBE_TASK,
                    "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "verdicts": verdicts}, indent=1) + "\n")
    for m, v in verdicts.items():
        print(f"SONDE {m}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
