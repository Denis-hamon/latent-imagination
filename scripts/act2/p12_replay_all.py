"""P12 — pilote du rejeu. Idempotent, une image tirée puis SUPPRIMÉE à la fois."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p12_replay import CORPUS, D, OUT, cname  # noqa: E402
from p9_replay import sh  # noqa: E402


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sel = json.loads((D / f"{CORPUS}-selection.json").read_text())
    for i, s in enumerate(sel, 1):
        iid = s["instance_id"]
        f = OUT / f"{iid}.json"
        if f.exists():
            d = json.loads(f.read_text())
            if "trajectories" in d or "ecartee" in d:
                print(f"[{i:3d}/{len(sel)}] {iid} — déjà fait", flush=True)
                continue
        print(f"[{i:3d}/{len(sel)}] {iid}", flush=True)
        r = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("p12_replay.py")), "run", iid],
            capture_output=True, timeout=7200)
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
        print("\n".join("        " + l for l in out.strip().splitlines()[-9:]), flush=True)
        sh(f"docker rm -f {cname(iid)} >/dev/null 2>&1; "
           f"docker rmi -f {s['docker_image']} >/dev/null 2>&1; true", t=900)
    print("terminé", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
