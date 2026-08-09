#!/usr/bin/env python3
"""E1 : Boltzmann-échantillonneur de diffs guidé par l'énergie latente.

Pour chaque tâche gelée (32) : générer K=4 diffs candidats (T=0.7, température
élevée de diversité), les scorer par distance latente au but (uniXCoder),
soumettre le min-énergie à torch-éval F2P sur le node.

Compare mesurée :
- taux de succès quand on prend le diff le plus proche du gold dans le latent
  (guidage énergie)
- vs taux quand on en prend un au hasard par tâche (contrôle).

Tous les diffs générés + scores enregistrés dans boltzmann-out.json (Mac) puis
l'éval F2P sur le node (bolt-f2p.json rapatrié). Log d'appels ajouté au budget.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
LOG = PILOT / "call-log.jsonl"
OUT = PILOT / "boltzmann-out.json"

K_CANDIDATES = 4
MODEL = os.environ.get("PILOT_MODEL", "Qwen/Qwen3.6-35B-A3B-FP8")
GALERE = "https://ai.galere.org/v1/chat/completions"
BOLTZ_TEMP = 0.7


def call_model(prompt: str) -> dict:
    key = os.environ.get("LI_GALERE_KEY") or os.environ.get("OPENCODE_GALERE_KEY")
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                       "temperature": BOLTZ_TEMP, "max_tokens": 6000})
    cmd = ["curl", "-sS", "--max-time", "580", "-X", "POST", GALERE,
           "-H", "Content-Type: application/json", "-H", "User-Agent: opencode/1.0",
           "--data-binary", "@-"]
    if key:
        cmd += ["-H", f"Authorization: Bearer {key}"]
    p = subprocess.run(cmd, input=body.encode(), capture_output=True, check=False)
    j = json.loads(p.stdout.decode())
    m = j["choices"][0]["message"]
    return {"text": (m.get("content") or "") + "\n" + (m.get("reasoning") or m.get("reasoning_content") or ""),
            "usage": j.get("usage", {})}


def extract_diff(text: str) -> str:
    import re
    m = re.search(r"```(?:diff|patch)\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"(?ms)^--- [ab]/.+", text)
    return m.group(0) if m else ""


def task_prompt(task: dict, src: str) -> str:
    return ("Fix failing tests. Output ONLY a unified diff in ```diff fences. "
            "No prose.\n"
            f"File at: {task['target']}\n\nTASK: {task['problem'][:900]}\n\n"
            f"FAILING TESTS: {'; '.join(task['f2p'][:4])}\n\n"
            f"CURRENT CONTENT (verbatim):\n```python\n{src}\n```")


def main() -> int:
    # panel figé = les 32 tâches du rapport act2, reconstruites honnêtement depuis
    # les métas des résultats déjà collectés (jamais confondu avec extension-128).
    tasks = json.loads((PILOT / "pilot-tasks-frozen32.json").read_text())
    res_root = PILOT / "boltzmann-e1"
    res_root.mkdir(exist_ok=True)
    res_root.mkdir(exist_ok=True)
    out_rows = []
    calls = 0
    for ti, t in enumerate(tasks):
        key = t["instance_id"].replace("/", "_")
        src_p = PILOT / f"{key}.buggy.py"
        if not src_p.is_file():
            continue
        src = src_p.read_text()
        cands = []
        for k in range(K_CANDIDATES):
            g = call_model(task_prompt(t, src))
            calls += 1
            diff = extract_diff(g["text"])
            f = res_root / f"{key}-cand{k}.diff"
            f.write_text(diff)
            cands.append({"k": k, "diff_file": str(f), "diff_len": len(diff)})
        out_rows.append({"task": t["instance_id"], "image": t["image"], "target": t["target"],
                         "f2p": t["f2p"], "candidates": cands})
        print(f"[{ti+1}/{len(tasks)}] {t['instance_id'][:40]:40} {len(cands)} cands, calls={calls}", flush=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps({"ts": datetime.now(UTC).isoformat(), "pilot_calls": calls,
                             "passage": "e1-boltzmann-gen"}) + "\n")
    OUT.write_text(json.dumps(out_rows, indent=1))
    print("boltzmann-out.json écrit —", len(out_rows), "tâches, appels:", calls)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
