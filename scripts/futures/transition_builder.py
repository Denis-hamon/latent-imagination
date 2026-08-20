#!/usr/bin/env python3
"""v39 — construction des transitions séquentielles (red_t + diff_{t+1}).

Lit replay-rows-v32..v38, garde les paires de tours appliqués consécutifs
par (instance, modèle), exporte jsonl pour le bras v39.
Run: uv run python scripts/futures/transition_builder.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NH = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest"
MSWB = ROOT / "data" / "landing" / "act2-pilot" / "mswb"
OUT = ROOT / "data" / "landing" / "act2-pilot" / "transitions"
WINDOWS = ("v32", "v33", "v34", "v35", "v36", "v37", "v38")
KEY_MODEL = {"DeepSeek-V4-Pro": "pro", "Qwen3.8-2.4T-A95B-NVFP4": "qwen",
             "GLM-5.2-NVFP4": "glm", "gemma-4-31B-it": "gemma",
             "NVIDIA-Nemotron-3-Super-120B-A12B-MLX": "nemotron"}


def load_declared() -> dict:
    dec = {}
    for repo in ("vuejs__core", "iamkun__dayjs"):
        f = MSWB / repo / "verified-mswb.json"
        if f.is_file():
            for t in json.loads(f.read_text()):
                if isinstance(t, dict):
                    dec[t["issue"]] = sorted(set(t.get("f2p", [])))
    return dec


def main() -> int:
    dec = load_declared()
    trans = []
    for w in WINDOWS:
        f = NH / f"replay-rows-{w}.jsonl"
        if not f.is_file():
            continue
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        by = defaultdict(list)
        for r in rows:
            if r.get("applied") and r.get("turn") and r.get("failed_all") is not None:
                by[(r["issue"], r.get("model", "?"))].append(r)
        for (issue, model), seq in by.items():
            seq.sort(key=lambda r: r["turn"])
            declared = dec.get(issue, [])
            if not declared:
                continue
            for a, b in zip(seq, seq[1:]):
                if b["turn"] != a["turn"] + 1:
                    continue
                slug = issue.replace("/", "_")[:80]
                df = NH / f"replay-{w}" / f"{slug}--{KEY_MODEL.get(model, '?')}" / f"t{b['turn']}.diff"
                if not df.is_file():
                    continue
                red_a = sorted(set(a["failed_all"]))
                red_b = sorted(set(b["failed_all"]))
                trans.append({
                    "key": f"{w}-{issue}-{KEY_MODEL.get(model, model)}-{a['turn']}>{b['turn']}",
                    "instance": issue, "window": w, "model": model,
                    "turn_from": a["turn"], "turn_to": b["turn"],
                    "declared": declared, "red_from": red_a, "red_to": red_b,
                    "red_from_dec": sorted(set(red_a) & set(declared)),
                    "red_to_dec": sorted(set(red_b) & set(declared)),
                    "diff_to": df.read_text()[:8000],
                    "changed": red_a != red_b})
    OUT.mkdir(exist_ok=True)
    (OUT / "v39-transitions.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in trans) + "\n")
    nch = sum(1 for t in trans if t["changed"])
    ntr = sum(1 for t in trans if t["red_to_dec"])
    insts = len({t["instance"] for t in trans})
    print(f"transitions : {len(trans)} ({nch} avec changement) sur {insts} instances ; "
          f"{ntr} avec red_to non vide ; paires déclarées {sum(len(t['declared']) for t in trans)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
