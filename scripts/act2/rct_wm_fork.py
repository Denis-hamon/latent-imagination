#!/usr/bin/env python3
"""RCT WM-context — arms B0/B1 par fork du MÊME draft existant (draw-3 off-arm).

Design (pré-enregistrement : governance/act2/rct-prereg-v1.md) :
  - arm A = draw-3 off-arm, déjà exécuté (9/32 F2P) — 0 call
  - draft = le patch diffusé à draw-3 (sync node → data/landing/act2-pilot/results/)
  - arm b0 : 1 appel "review generic" (contrôle 2ᵉ chance) + 1 apply-retry max
  - arm b1 : 1 appel avec bloc CONSEQUENCE-CONTEXT (wm_context) + 1 apply-retry max
  - cap pré-enregistré : 100 calls galere, arrêt dur, publication partielle avec %

Sortie : data/landing/act2-pilot/rct-v1/results/{task}-{b0,b1}/patch.diff + meta.json
(node-exec compatible : pilot_node_exec.py avec PILOT_ARMS=b0,b1 PILOT_CAMPAIGN_DIR=rct-v1).

--dry-run : zéro appel galere, draft factice, vérifie layout+contexte end-to-end.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "act2"))
import pilot_run as pr                    # call_model, extract_*, apply_*, make_diff
import wm_context

PILOT = ROOT / "data" / "landing" / "act2-pilot"
RCT = PILOT / "rct-v1"
JOBS = RCT / "results"
DRAFTS = PILOT / "results"               # sync depuis le node (slots *-off de draw-3)
CAP = 100
LOG = RCT / "call-log.jsonl"

NEUTRAL = ("Review your draft patch and produce an improved unified diff. "
           "Output ONLY a unified diff inside ```diff fences — no prose.")


def log_call(**kw):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"ts": datetime.now(UTC).isoformat(), **kw}) + "\n")


def calls_used() -> int:
    return sum(1 for _ in LOG.open()) if LOG.is_file() else 0


def base_prompt(task: dict, src: str) -> str:
    """Prompt identique à celui de l'arm A (pilot_run.gen_patch)."""
    return ("Fix failing tests. Output ONLY a unified diff inside ```diff fences "
            "(paths a/<file> b/<file>). The diff must apply with `git apply`. No prose.\n"
            f"File to patch: {task.get('target', 'the affected file')}\n\n"
            f"TASK: {task['problem'][:1200]}\n\nFAILING TESTS: {'; '.join(map(str, task['f2p'][:6]))}\n\n"
            f"CURRENT CONTENT (verbatim):\n```python\n{src}\n```")


def extract_diff_v2(text: str) -> str | None:
    """Extraction consolidée (amendement 2026-08-10a) — corrige deux bugs de chaîne :
    (1) extract_diff ne capturait que le 1er bloc fenced (Qwen émet des dizaines de
        blocs de raisonnement → diff capture partielle) ;
    (2) sanitize_diff terminait au 1er ligne vide (les lignes de contexte vides
        perdent leur espace préfixe à la génération → hunk tronqué à l'entête).
    L'applieur (apply_and_export_debug, git apply --recount) est inchangé.
    Côté b0/b1 seulement : la chaîne d'extraction de l'arm A reste celle de draw-3."""
    import re
    blocks = re.findall(r"```(?:diff|patch)\n(.*?)```", text, re.DOTALL)
    if blocks:
        raw = "\n".join(blocks)
    else:
        m = re.search(r"(?ms)^diff --git .+", text) or \
            re.search(r"(?ms)^--- [ab]/.+\n\+\+\+ [ab]/.+\n@@ .+", text)
        raw = m.group(0) if m else None
    if raw is None:
        return None
    keep, started = [], False
    prefixes = ("--- ", "+++ ", "@@ ", "index ", "diff --git ", "new file", "old mode", "new mode")
    for ln in raw.splitlines():
        s = ln.rstrip()
        if s.startswith(("+diff>", "</diff>", "</patch>", "</change>")):
            continue
        if s.startswith(prefixes) or s.startswith(("-", "+", " ", "\\ ")):
            keep.append(s)
            started = True
        elif not started:
            continue
        elif s == "":
            keep.append(" ")          # ligne vide dans un hunk = ligne de contexte vide
        else:
            break
    out = "\n".join(keep)
    return (out + "\n") if out else None


def extract_and_apply(task: dict, src: str, reply: str) -> tuple[str | None, str, str]:
    """Full-file > diff consolidé v2 > git apply local (applieur canonique)."""
    original = src
    edited = pr.extract_full_file(reply)
    if edited and original:
        if len(edited.splitlines()) < len(original.splitlines()) * 0.5:
            edited = None
    if edited and original and edited.strip() != original.strip():
        return pr.make_diff(original, edited, task["target"]), "regenerated", ""
    raw = extract_diff_v2(reply)
    if raw and original:
        d, err = pr.apply_and_export_debug(original, raw + "\n", task["target"])
        return d, ("model-applied-reexport" if d else "unappliable"), ("" if d else err)
    return None, "no-diff", ""


def run_arm(task: dict, src: str, draft: str, arm: str, dry: bool) -> dict:
    """arm b0 (feedback neutre) ou b1 (bloc WM). 1 appel + 1 apply-retry."""
    iid = task["instance_id"]
    key = iid.replace("/", "_")
    outdir = JOBS / f"{key}-{arm}"
    outdir.mkdir(parents=True, exist_ok=True)
    if (outdir / "patch.diff").is_file():
        return {"task": iid, "arm": arm, "skipped": "exists"}

    if arm == "b1":
        ctx = wm_context.build_context(task["problem"], task["f2p"], draft, exclude_task=iid)
        ask = ("YOUR PREVIOUS DRAFT (below) was instrumented against a world model of "
               "113 past patches on OTHER tasks.\n" + ctx +
               "\n\nYOUR PREVIOUS DRAFT:\n```diff\n" + (draft[:3000] or "(no appliable diff)") +
               "\n```\nImprove it. HARD CONSTRAINT: the unified diff must target ONLY "
               f"a/{task['target']} (paths a/<file> b/<file> on that same file) so plain "
               "`git apply` accepts it. One single ```diff fenced block, no prose.")
    else:
        ask = ("YOUR PREVIOUS DRAFT:\n```diff\n" + (draft[:3000] or "(no appliable diff)") +
               "\n```\n" + NEUTRAL +
               f" HARD CONSTRAINT: the diff must target ONLY a/{task['target']} "
               "(single ```diff block, applies with `git apply`).")
    prompt = base_prompt(task, src) + "\n\n" + ask

    if dry:
        (outdir / "meta.json").write_text(json.dumps(
            {"task": iid, "arm": arm, "dry_run": True,
             "ctx_preview": (ctx[:400] if arm == "b1" else "")}, indent=1))
        return {"task": iid, "arm": arm, "dry": True}

    if calls_used() >= CAP:
        raise SystemExit(f"cap {CAP} atteint — publication partielle (voir prereg)")

    g = pr.call_model(prompt)
    log_call(task=iid, arm=arm, kind="fork",
             prompt_sha256=sha256(prompt.encode()).hexdigest(),
             reply_sha256=sha256(g["text"].encode()).hexdigest(), usage=g["usage"])
    diff, mode, err = extract_and_apply(task, src, g["text"])
    attempts = [{"n": 1, "mode": mode, "apply_stderr": err[-400:] if err else ""}]

    if not diff:    # apply-retry instrumenté, 1 fois max (protocole v3)
        if calls_used() >= CAP:
            raise SystemExit(f"cap {CAP} atteint — publication partielle (prereg)")
        fb = err or "no parseable diff (must contain one ```diff block)"
        g2 = pr.call_model(prompt + f"\n\nYOUR PREVIOUS ATTEMPT FAILED — git-apply feedback:\n"
                                    f"```\n{fb[:800]}\n```\nProduce a corrected diff.")
        log_call(task=iid, arm=arm, kind="apply-retry",
                 reply_sha256=sha256(g2["text"].encode()).hexdigest(), usage=g2["usage"])
        diff, mode, err = extract_and_apply(task, src, g2["text"])
        attempts.append({"n": 2, "mode": mode})

    meta = {"task": iid, "arm": arm, "run_at": datetime.now(UTC).isoformat(),
            "draft_sha256": sha256((draft or "").encode()).hexdigest(),
            "attempts": attempts,
            "patch_sha256": sha256((diff or "").encode()).hexdigest() if diff else None}
    if diff:
        (outdir / "patch.diff").write_text(diff)
    (outdir / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tasks = json.loads((PILOT / "pilot-tasks-frozen32.json").read_text())
    JOBS.mkdir(parents=True, exist_ok=True)
    (RCT / "pilot-tasks.json").write_text(json.dumps(tasks, indent=1))  # manifest node
    res = []
    for task in tasks:
        iid = task["instance_id"]
        key = iid.replace("/", "_")
        src_p = PILOT / f"{key}.buggy.py"
        src = src_p.read_text() if src_p.is_file() else ""
        draft_p = DRAFTS / f"{key}-off" / "patch.diff"
        draft = draft_p.read_text() if draft_p.is_file() else ""
        if not args.dry_run and not draft_p.is_file():
            print(f"WARN draft absent pour {iid} — fork intent-to-treat sans diff")
        for arm in ("b0", "b1"):
            m = run_arm(task, src, draft, arm, args.dry_run)
            res.append(m)
            print(f"{key[:52]:52s} {arm} {'dry' if args.dry_run else m.get('patch_sha256', 'NO-DIFF')}",
                  flush=True)
    print(f"\nslots traités: {len(res)} | calls consommés: {calls_used()} / cap {CAP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
