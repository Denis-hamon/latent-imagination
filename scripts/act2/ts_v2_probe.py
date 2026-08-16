#!/usr/bin/env python3
"""Window coverage-ts-v2 — DIFFICULTY-PROBE pré-gel du quota (leçon rétro 14).

Étape 1 (zéro appel) : vérifier la chaîne sur 2 mutants difficiles des
content-adapters kimsufi — mutation → F2P nommés rouges (vitest remote) →
restauration verte. Étape 2 (appels comptés à l'enveloppe v2) : 2 générations
de l'auteur épinglé (T=0.7, classe prompt pilot_run gelée, fuzz-lane) sur ces
mutants ; log audité dans coverage-ts-2/call-log.jsonl.

Règle de décision GELÉE dans la fenêtre : ≥1 échec auteur ⇒ classe de
difficulté validée ; 2/2 réparés ⇒ escalade déclarée (max 2).
Run: uv run python scripts/act2/ts_v2_probe.py --stage verify|author
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
Q = PILOT / "coverage-ts-2"
HOST = "Kimsufi-standard"
REMOTE = "~/kimsufi-source/apps/site"
SPEC_ROOT = "src/content-adapters/drupal"

MUTANTS = [
    {
        "task_id": "kimsufi__slider.region_sort_inverted",
        "file": f"{SPEC_ROOT}/transformers.ts",
        "spec": "transformers.slider",
        "replacements": [
            ("    (a, b) => getSlideRegionIndex(a) - getSlideRegionIndex(b)",
             "    (a, b) => getSlideRegionIndex(b) - getSlideRegionIndex(a)"),
        ],
        "problem": "Le tri des slides par index de région est inversé : les cartes "
                   "s'affichent dans l'ordre inverse de la région Drupal, et les "
                   "enfants sans région remontent au début au lieu d'aller à la fin.",
    },
    {
        "task_id": "kimsufi__slider.price_html_not_stripped",
        "file": f"{SPEC_ROOT}/transformers.ts",
        "spec": "transformers.slider",
        "replacements": [
            ("const priceValue = rawPriceHtml ? rawPriceHtml.replace(/<[^>]*>/g, '').trim() : '';",
             "const priceValue = rawPriceHtml ? rawPriceHtml.trim() : '';"),
        ],
        "problem": "Le prix du slider n'est plus nettoyé de ses balises HTML : la "
                   "valeur retournée contient le markup brut (<p>79,99 €</p> au lieu "
                   "de 79,99 €).",
    },
]


def sh_local(cmd: list[str], **kw):
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def sh_remote(cmd: str, timeout: int = 300):
    return sh_local(["ssh", "-o", "ConnectTimeout=12", HOST, cmd], timeout=timeout)


def verify_stage() -> int:
    Q.mkdir(parents=True, exist_ok=True)
    results = []
    for m in MUTANTS:
        print(f"chaîne {m['task_id']} …", flush=True)
        st = sh_remote(f"cd {REMOTE} && git status --porcelain | head -1")
        if st.returncode != 0 or st.stdout.strip():
            print("  ABORT: worktree remote non propre")
            return 2
        r = sh_remote(f"cd {REMOTE} && cat {m['file']}", timeout=120)
        if r.returncode != 0:
            print("  ABORT: lecture fichier remote")
            return 2
        orig = r.stdout
        bug = orig
        for old, new in m["replacements"]:
            if old not in bug:
                print("  ABORT: texte mutant introuvable")
                return 3
            bug = bug.replace(old, new, 1)
        # push du fichier muté + vitest + restauration
        tmp = Q / f".probe-{m['task_id'][-12:]}.tsx"
        tmp.write_text(bug)
        up = sh_local(["scp", "-q", str(tmp), f"{HOST}:{REMOTE}/{m['file']}"], timeout=120)
        tmp.unlink(missing_ok=True)
        if up.returncode != 0:
            print("  ABORT: scp failed"); return 2
        vt = sh_remote(f"cd {REMOTE} && ./node_modules/.bin/vitest run {m['spec']} --reporter=json 2>/dev/null")
        sh_remote(f"cd {REMOTE} && git checkout -- {m['file']}")
        chk = sh_remote(f"cd {REMOTE} && git status --porcelain | head -1")
        failed, passed = [], []
        try:
            raw = vt.stdout
            d = json.loads(raw[raw.find("{"):])
            for tr in d.get("testResults", []):
                for a in tr.get("assertionResults", []):
                    (failed if a.get("status") == "failed" else passed).append(a.get("title", ""))
        except (json.JSONDecodeError, ValueError):
            print("  ABORT: parse vitest impossible"); return 3
        if chk.stdout.strip():
            print("  ABORT: restauration remote a échoué"); return 2
        entry = {"task_id": m["task_id"], "f2p": failed, "p2p_n": len(passed),
                 "file": m["file"], "problem": m["problem"],
                 "buggy_sha256": sha256(bug.encode()).hexdigest()}
        (Q / f"{m['task_id'].replace('/', '_')}.buggy.py").write_text(bug)
        results.append(entry)
        print(f"  F2P: {len(failed)} | P2P verts: {len(passed)} | arbre restauré")
        if not failed:
            print("  RÉFUSÉ : le mutant ne casse rien — chaîne invalide")
            return 3
    (Q / "probe-manifest.json").write_text(
        json.dumps({"window": "coverage-ts-v2", "stage": "verify",
                    "mutants": results,
                    "at": datetime.now(UTC).isoformat().replace("+00:00", "Z")},
                   indent=1) + "\n")
    print(f"vérification chaîne OK pour {len(results)} mutants → probe-manifest.json")
    return 0


def author_stage() -> int:
    mani = json.loads((Q / "probe-manifest.json").read_text())
    # harness budget : log scopé coverage-ts-2 (enveloppe v2, cap 90)
    log = Q / "call-log.jsonl"
    spec = importlib.util.spec_from_file_location("gg", ROOT / "scripts" / "act2" / "genfam_gen.py")
    gg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gg)
    spec2 = importlib.util.spec_from_file_location("pr2", ROOT / "scripts" / "act2" / "pilot_run.py")
    pr = importlib.util.module_from_spec(spec2)
    sys.modules["pilot_run"] = pr
    spec2.loader.exec_module(pr)
    pr.call_model = gg.call_t07  # wrapper gelé T=0.7 / auteur épinglé / 16k
    MODEL = gg.MODEL
    rows = []
    for m in mani["mutants"]:
        task = {"instance_id": m["task_id"], "problem": m["problem"],
                "f2p": m["f2p"][:6], "target": m["file"]}
        os.environ["PILOT_CAMPAIGN_DIR"] = "coverage-ts-2"
        pr.os.environ["PILOT_CAMPAIGN_DIR"] = "coverage-ts-2"
        (Q / f"{m['task_id'].replace('/', '_')}.buggy.py").exists() or sys.exit("buggy absent")
        try:
            g = pr.gen_patch(task)
            err = None
        except Exception as e:  # noqa: BLE001 — erreur endpoint auditée (S14)
            g, err = None, str(e)[:300]
        row = {"ts": datetime.now(UTC).isoformat(), "window": "coverage-ts-v2",
               "stage": "difficulty-probe", "slot": m["task_id"], "model": MODEL,
               "campaign": "coverage-ts-2", "temperature": 0.7}
        if err:
            row["error"] = err
        else:
            row.update({"prompt_sha256": g["prompt_sha256"],
                        "reply_sha256": g["reply_sha256"], "raw_reply": g["raw_reply"],
                        "usage": g["usage"]})
            san = pr.extract_diff_sanitized(g["raw_reply"])
            buggy = (Q / f"{m['task_id'].replace('/', '_')}.buggy.py").read_text()
            diff = mode = None
            if san:
                diff, _e = pr.apply_and_export_debug(buggy, san + "\n", m["file"])
                mode = "strict-git" if diff else None
                if diff is None:
                    diff, _e2 = gg.apply_fuzz_reexport(buggy, san + "\n", m["file"])
                    mode = "fuzz-reexport" if diff else None
            row.update({"diff_mode": mode,
                        "diff_sha256": sha256(diff.encode()).hexdigest() if diff else None})
            if diff:
                (Q / f"{m['task_id'].replace('/', '_')}-probe.diff").write_text(diff)
        with log.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        rows.append(row)
        print(f"{m['task_id']}: " +
              (f"diff produit ({row.get('diff_mode')})" if row.get("diff_sha256")
               else f"PAS DE DIFF {'(erreur endpoint — ' + row['error'][:40] + ')' if 'error' in row else '(no-diff)'}"))
    n_diff = sum(1 for r in rows if r.get("diff_sha256"))
    print(f"\nSONDE AUTEUR : {n_diff}/{len(rows)} mutants réparés par l'auteur")
    verdict = ("CLASSE VALIDÉE (≥1 échec) — gel du quota sur cette classe"
               if n_diff < len(rows) else
               "2/2 réparés — ESCALADE de difficulté requise avant gel (règle fenêtre)")
    (Q / "probe-verdict.json").write_text(json.dumps(
        {"window": "coverage-ts-v2", "n_mutants": len(rows),
         "n_author_repaired": n_diff, "verdict": verdict,
         "at": datetime.now(UTC).isoformat()}, indent=1) + "\n")
    print(verdict)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("verify", "author"), required=True)
    a = ap.parse_args()
    sys.exit(verify_stage() if a.stage == "verify" else author_stage())
