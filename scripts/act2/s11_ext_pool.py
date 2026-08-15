#!/usr/bin/env python3
"""S11 — extension du pool latent par trajectoires EXTERNES labellisées (0 call galere).

Pré-déclaration ( inline, même classe que S5/S7 — extension de pool avec mixture
déclarée, mesurée avant toute promotion ; aucune règle de gate n'est touchée ) :

Source : HF SWE-bench/SWE-smith-trajectories (MIT, 8 shards ticks-*) via
  l'adapter sanctionné public_corpora.fetch_smith_matched
  (~3229 trajectoires/shard d'agents externes — claude-3.7/3.5, gpt-4o — sur
  tâches SWE-smith).
  CORRECTION 2026-08-14 (le join initial du 11/08 est remplacé, jamais évalué
  ni publié) : la colonne `patch` de l'export HF est DÉSALIGNÉE de sa colonne
  `instance_id` (mesuré : 15910/16052 diffs dans un autre repo que la tâche).
  Le diff final de l'agent est reconstruit depuis la colonne `messages`
  (trajectoire SWE-agent : dernier bloc <diff>…</diff> de l'observation de
  submit — le texte TEL QU'ÉCRIT par l'agent, conforme à la règle produit S6).
  Alignement vérifié sur sonde : 97 % des diffs extraits partagent ≥1 fichier
  avec le gold de la tâche ; colonne `resolved` cohérente avec la présence du
  diff de submit (77 % vs 79 % non-résolus). `resolved` = verdict du harness
  officiel de la tâche = label juge-free, même classe de validité que les
  labels pool ; risque résiduel de désalignement couvert par le critère poison.
Jointure : swe-smith-tasks (HF SWE-bench/SWE-smith, MIT, fetch via l'adapter
  sanctionné public_corpora) → state = problem[:1200] + "\\n" + "; ".join(f2p[:6])
  (recette exacte embed_pool.py), gold = patch de la tâche (vrai fix).
Dédup : sha256(diff.strip()) contre pool v6 + interne (précédent S5).

Mixture DÉCLARÉE : auteurs externes (claude-3.7 majoritairement) vs pool v6
  (modèles galere). Risques assumés à mesurer, pas à nier :
  - label `resolved` pris sur parole du dataset exporté → falsification interne :
    si le label était bruit, l'AUC ext-seule tombe à ~0.5 (critère POISON < 0.65,
    même classe que recovered = 0.543 en S6) ;
  - patchs multi-fichiers possibles vs pool 95 % mono-hunk → dérive géométrique
    visible dans la stratification de la queue haute-confiance.

Contrôle positif OBLIGATOIRE : v6 seul GOLD uxc doit reproduire AUC 0.822 /
acc 0.779 (tolérances S10) — sinon STOP, rien n'est publié.

Critères enregistrés AVANT mesure :
  - ext seul : AUC ≥ 0.65 → candidats sains ; < 0.65 → POISON, pool v6 inchangé ;
  - v7 = v6 + ext : GOLD et GxF λ=1 réévalués LOAO ; toute promotion du pool ou
    du modèle reste à la main de l'owner sous la règle v2 (AUC > 0.864 ET cov > 30 %)
    — CE SCRIPT NE PROMEUT RIEN.

Sorties : data/landing/act2-pilot/s11-ext-pool.json (+ .npz si stage embed),
          data/landing/act2-pilot/s11-pool-v7.json (mesures).

Stages : --stage join  (fetch+join+dedup, .venv, réseau public HF)
         --stage all   (embed uxc CLS-512 + éval LOAO, .venv-embed)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

_SUBMIT_DIFF_RE = re.compile(r"<diff>\r?\n(.*)</diff>", re.S)


def extract_last_diff(messages_json):
    """Dernier diff de submit d'une trajectoire SWE-agent (<diff>…</diff> dans
    une observation), normalisé LF. None si la conversation n'en contient pas."""
    try:
        msgs = json.loads(messages_json)
    except (TypeError, ValueError):
        return None
    best = None
    for m in msgs:
        c = str(m.get("content"))
        if "</diff>" not in c:
            continue
        found = _SUBMIT_DIFF_RE.findall(c)
        if found:
            best = found[-1].strip().replace("\r\n", "\n").replace("\r", "\n")
    return best

try:
    import numpy as np
except ModuleNotFoundError:  # le stage join n'en a pas besoin (.venv repo)
    np = None

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
LANDING = ROOT / "data" / "landing"
TRAJ_DIR = LANDING / "swe-smith-trajectories" / "smith-matched-full" / "raw"
TRAJ_SHARDS = 8
TASKS_DIR = LANDING / "swe-smith-tasks" / "smith-tasks-v1" / "raw"
ART = ROOT / "packages" / "latent-gate" / "public" / "artifacts"

COVERAGES = (1.0, 0.5, 0.3, 0.25, 0.2, 0.1)
TARGET = 0.95
EXT_JSON = PILOT / "s11-ext-pool.json"
EXT_NPZ = PILOT / "s11-ext-pool.npz"


# ---------------------------------------------------------------- protocole S10
def norm(A):
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def wilson(k, n):
    z = 1.96
    p = k / max(1, n)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return max(0.0, c - h), min(1.0, c + h)


def auc(succ, fail):
    """Mann-Whitney par rangs (l'outer product n_pos×n_neg explose à n≈16 k)."""
    if not len(succ) or not len(fail):
        return float("nan")
    s = np.concatenate([succ, fail])
    n1 = len(succ)
    order = s.argsort(kind="mergesort")
    ranks = np.empty(len(s), float)
    ranks[order] = np.arange(1, len(s) + 1)
    vals, inv, counts = np.unique(s, return_inverse=True, return_counts=True)
    sums = np.zeros(len(vals))
    np.add.at(sums, inv, ranks)
    ranks = sums[inv] / counts[inv]
    r1 = ranks[:n1].sum()
    return float((r1 - n1 * (n1 + 1) / 2) / (n1 * len(fail)))


def logreg_fit(X, y, lam=1.0, iters=200):
    Xb = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(Xb.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(Xb @ w)))
        g = Xb.T @ (p - y) + lam * w
        W = p * (1 - p) + 1e-9
        H = (Xb * W[:, None]).T @ Xb + lam * np.eye(Xb.shape[1])
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def loao_energy(cd, cg, y, tasks):
    """Énergie 1−<cd,cg> + marge au seuil médiane-train, LOAO."""
    n = len(y)
    energy = 1.0 - (cd * cg).sum(-1)
    pred = np.zeros(n, int)
    conf = np.zeros(n)
    for held in sorted(set(tasks)):
        te = tasks == held
        thr = np.median(energy[~te])
        pred[te] = (energy[te] < thr).astype(int)
        conf[te] = np.abs(energy[te] - thr)
    return pred, conf, -energy


def _loao_f1_features(cd, tasks, y, chunk=1024):
    """Pour chaque ligne : dist au négatif le plus proche − dist au positif le
    plus proche, la propre tâche exclue des voisins = la valeur exacte du fold
    LOAO où cette tâche est held-out (calcul par chunks, pas de n×n global)."""
    n = len(y)
    cd = cd.astype(np.float32)
    f1 = np.full(n, np.nan)
    pos_idx = np.where(y == 1)[0]
    neg_idx = np.where(y == 0)[0]
    tp, tn = tasks[pos_idx], tasks[neg_idx]
    for i0 in range(0, n, chunk):
        sl = slice(i0, min(i0 + chunk, n))
        S = cd[sl] @ cd.T
        tt = tasks[sl]
        for idx, tl, which in ((pos_idx, tp, "pos"), (neg_idx, tn, "neg")):
            D = 1.0 - S[:, idx]
            D[tt[:, None] == tl[None, :]] = np.inf  # voisine de la même tâche exclue
            if which == "pos":
                dp = D.min(1)
            else:
                dn = D.min(1)
        finite = np.isfinite(dn) & np.isfinite(dp)
        v = dn - dp
        v[~finite] = 0.0
        f1[sl] = v
    return f1


def gxf_loao(cd, cg, y, tasks):
    """GxF : [−energy, F1] logreg λ=1 par fold (champion S3/S7). Features F1
    précalculées exactes LOAO (voir _loao_f1_features) — l'ancienne version
    recalculait la sim-matrix par fold, impraticable à n≈16 k."""
    n = len(y)
    energy = 1.0 - (cd * cg).sum(-1)
    pred = np.zeros(n, int)
    conf = np.zeros(n)
    sco = np.zeros(n)
    f1 = _loao_f1_features(cd, tasks, y)
    skipped = 0
    for held in sorted(set(tasks)):
        te, tr = tasks == held, tasks != held
        y_tr = y[tr]
        if not y_tr.any() or y_tr.all():
            skipped += 1
            continue
        Ftr = np.column_stack([-energy[tr], f1[tr]])
        Fte = np.column_stack([-energy[te], f1[te]])
        mu, sd = Ftr.mean(0), Ftr.std(0) + 1e-9
        w = logreg_fit((Ftr - mu) / sd, y_tr)
        Xte = np.column_stack([np.ones(te.sum()), (Fte - mu) / sd])
        p = 1.0 / (1.0 + np.exp(-(Xte @ w)))
        pred[te] = (p > 0.5).astype(int)
        conf[te] = np.abs(p - 0.5)
        sco[te] = p
    if skipped:
        print(f"  gxf: {skipped} folds dégénérés sautés (train mono-classe)")
    return pred, conf, sco


def report(name, pred, conf, sco, y, maj):
    n = len(y)
    curve = []
    best = 0.0
    order = np.argsort(-conf)
    for cov in COVERAGES:
        m = max(1, int(round(n * cov)))
        sel = order[:m]
        k = int((pred[sel] == y[sel]).sum())
        lo, hi = wilson(k, m)
        curve.append({"coverage": cov, "n": m, "acc": k / m,
                      "wilson95": [lo, hi]})
        if k / m >= TARGET and lo > maj:
            best = max(best, cov)
    res = {"auc": auc(sco[y == 1], sco[y == 0]), "acc100": curve[0]["acc"],
           "max_cov": best, "curve": curve}
    print(f"{name:<38} AUC {res['auc']:.3f} | acc100 {res['acc100']:.3f} "
          f"| cov@≥0.95 {best:4.0%}", flush=True)
    return res


# ---------------------------------------------------------------- stage join
def stage_join() -> int:
    import pyarrow.parquet as pq

    from public_corpora.experiments import fetch_smith_matched
    from public_corpora.smith_tasks import fetch_smith_task_statements

    man_t = fetch_smith_matched(LANDING, shards=TRAJ_SHARDS,
                                batch_id="smith-matched-full")
    print(f"trajectoires fetchées: {man_t['item_count']} items "
          f"({man_t['shards']} shards)")
    man = fetch_smith_task_statements(LANDING, max_shards=11)
    print(f"tasks fetchés (manifest {man['batch_id']}): {man['task_count']}")

    tasks = {}
    for shard in sorted(TASKS_DIR.glob("train-*.parquet")):
        for r in pq.read_table(
                shard,
                columns=["instance_id", "problem_statement", "patch",
                         "FAIL_TO_PASS"]).to_pylist():
            f2p = [str(x) for x in (r["FAIL_TO_PASS"] or [])]
            tasks[r["instance_id"]] = (
                (r["problem_statement"] or "")[:1200] + "\n" + "; ".join(f2p[:6]),
                r["patch"] or "",
            )
    print(f"tâches indexées: {len(tasks)}")

    pool_rows = json.loads((ART / "latent-pool-v6.json").read_text())
    pool_tasks = {r["task"] for r in pool_rows}
    seen = {hashlib.sha256(r["diff"].strip().encode()).hexdigest()
            for r in pool_rows}

    def _files(d):
        return set(re.findall(r"diff --git a/(\S+)", d))

    rows, dedup, nojoin, empty, n_traj = [], 0, 0, 0, 0
    for shard in sorted(TRAJ_DIR.glob("ticks-*.parquet")):
      for t in pq.read_table(
              shard, columns=["instance_id", "model", "messages", "resolved"]
      ).to_pylist():
        n_traj += 1
        p = extract_last_diff(t.get("messages"))
        if not p or "diff --git" not in p:
            empty += 1
            continue
        if t["instance_id"] not in tasks:
            nojoin += 1
            continue
        h = hashlib.sha256(p.strip().encode()).hexdigest()
        if h in seen:
            dedup += 1
            continue
        seen.add(h)
        state, gold = tasks[t["instance_id"]]
        rows.append({
            "task": t["instance_id"], "arm": "ext", "campaign": "smith-ext-v1",
            "author": t.get("model", "?"),
            "state": state, "diff": p, "gold": gold,
            "y": 1 if t.get("resolved") else 0,
            "x_diff_source": "messages-last-submit",
            "x_shares_gold_file": bool(_files(p) & _files(gold)),
        })
    print(f"traj {n_traj} | sans diff submit {empty} | sans tâche {nojoin} | "
          f"dédup {dedup} | GARDÉS {len(rows)}")
    print(f"tâches nouvelles vs v6: "
          f"{len({r['task'] for r in rows} - pool_tasks)} / "
          f"{len({r['task'] for r in rows})}")
    pos = sum(r["y"] for r in rows)
    print(f"labels: {pos}/{len(rows)} positifs ({pos / max(1, len(rows)):.1%})")
    sg = [r["x_shares_gold_file"] for r in rows]
    print(f"audit alignement: partage ≥1 fichier gold — "
          f"résolus {sum(a and b for a, b in zip(sg, (r['y'] for r in rows)))}/"
          f"{pos} | non-résolus "
          f"{sum(a and not b for a, b in zip(sg, (r['y'] for r in rows)))}/"
          f"{len(rows) - pos}")
    EXT_JSON.write_text(json.dumps(rows, indent=1))
    print(f"OK: {EXT_JSON}")
    return 0


# ---------------------------------------------------------------- stage embed
def batched_embed(model, tok, texts, bs=8):
    """Stream par chunks → memmap disque (le pool 16k tient en RAM, mais le
    tokenizer rust forké multipliait le RSS — OOM observé à 27 GB sur node)."""
    import gc
    import os

    import torch
    n = len(texts)
    probe = model(**{k: v.to(model.device) for k, v in
                     tok(["probe"], return_tensors="pt").items()}
                  ).last_hidden_state[:, 0]
    dim = probe.shape[-1]
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"s11-embed-{id(texts)}.npy"
    mm = np.lib.format.open_memmap(tmp, mode="w+", dtype=np.float32,
                                   shape=(n, dim))
    import resource
    cap = 8192  # chars ≫ 512 tokens de code → troncature tokenizer inchangée,
    texts = [t[:cap] if len(t) > cap else t for t in texts]  # bit-équivalent
    for i in range(0, n, bs):
        tb = tok(texts[i:i + bs], padding=True, truncation=True, max_length=512,
                 return_tensors="pt")
        with torch.no_grad():
            v = model(**{k: t.to(model.device) for k, t in tb.items()}
                      ).last_hidden_state[:, 0]
        mm[i:i + bs] = v.detach().float().cpu().numpy()
        del tb, v
        if i % (bs * 250) == 0:
            mm.flush()
            gc.collect()
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
            print(f"  [{i}/{n}] maxRSS {rss:.1f} GB", flush=True)
    mm.flush()
    arr = np.array(mm)
    del mm
    tmp.unlink(missing_ok=True)
    return arr


def stage_embed(limit: int = 0) -> int:
    import gc
    import os

    os.environ["TOKENIZERS_PARALLELISM"] = "false"  # anti-fork (OOM S11 node)

    import torch
    from transformers import AutoModel, AutoTokenizer

    rows = json.loads(EXT_JSON.read_text())
    if limit:
        rows = rows[:limit]
    states = [r["state"] for r in rows]
    diffs = [r["diff"] for r in rows]
    goals = [r["gold"] for r in rows]
    del rows  # libère dicts/clés — les str restent partagées par les 3 listes
    gc.collect()
    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    device = ("cuda" if torch.cuda.is_available()
              else "mps" if torch.backends.mps.is_available() else "cpu")
    model = (AutoModel.from_pretrained("microsoft/unixcoder-base")
             .to(device).eval())
    print(f"encodeur uxc-base sur {device}, {len(states)} échantillons",
          flush=True)
    E_s = batched_embed(model, tok, states)
    print("state ok", flush=True)
    E_d = batched_embed(model, tok, diffs)
    print("diff ok", flush=True)
    E_g = batched_embed(model, tok, goals)
    print("goal ok", flush=True)
    np.savez_compressed(EXT_NPZ, E_state=E_s, E_diff=E_d, E_goal=E_g)
    print(f"OK: {EXT_NPZ}")
    return 0


# ---------------------------------------------------------------- stage eval
def _v6(name: str) -> Path:
    """Pool v6 : artifacts du package si présents, sinon copie déposée au pilot."""
    art = ART / name
    return art if art.exists() else PILOT / name


def stage_eval() -> int:
    rows6 = json.loads(_v6("latent-pool-v6.json").read_text())
    rowsX = json.loads(EXT_JSON.read_text())
    du = np.load(_v6("latent-pool-v6.npz"))
    dx = np.load(EXT_NPZ)

    out = {"n_v6": len(rows6), "n_ext": len(rowsX), "variants": {}}

    # --- contrôle positif obligatoire : v6 seul, recette champion ---
    y6 = np.array([int(r["y"]) for r in rows6])
    t6 = np.array([r["task"] for r in rows6])
    maj6 = max(y6.mean(), 1 - y6.mean())
    EU6 = {k: norm(du[k]) for k in ("E_state", "E_diff", "E_goal")}
    cd6 = norm(EU6["E_state"] + EU6["E_diff"])
    cg6 = norm(EU6["E_state"] + EU6["E_goal"])
    pred, conf, sco = loao_energy(cd6, cg6, y6, t6)
    ctrl = report("CTRL v6 GOLD (=S7/S10)", pred, conf, sco, y6, maj6)
    ok = abs(ctrl["auc"] - 0.822) < 0.01 and abs(ctrl["acc100"] - 0.779) < 0.005
    print(f"  → contrôle {'OK' if ok else 'DÉRIVE — STOP'}")
    out["positive_control"] = {"expected": [0.822, 0.779],
                               "got": [ctrl["auc"], ctrl["acc100"]], "ok": ok}
    if not ok:
        (PILOT / "s11-pool-v7.json").write_text(json.dumps(out, indent=1))
        return 1

    # --- ext seul : contrôle poison (critère déclaré AUC ≥ 0.65) ---
    yX = np.array([int(r["y"]) for r in rowsX])
    tX = np.array([r["task"] for r in rowsX])
    majX = max(yX.mean(), 1 - yX.mean())
    EUX = {k: norm(dx[k]) for k in ("E_state", "E_diff", "E_goal")}
    cdX = norm(EUX["E_state"] + EUX["E_diff"])
    cgX = norm(EUX["E_state"] + EUX["E_goal"])
    pred, conf, sco = loao_energy(cdX, cgX, yX, tX)
    out["n_ext_tasks"] = len(set(tX))
    out["majority_ext"] = float(majX)
    out["variants"]["ext_seul_gold"] = report(
        "EXT seul GOLD (poison<0.65)", pred, conf, sco, yX, majX)
    poison = out["variants"]["ext_seul_gold"]["auc"] < 0.65
    out["poison"] = bool(poison)
    if poison:
        print("POISON DÉCLARÉ (critère pré-enregistré) — pool v6 inchangé.")
        (PILOT / "s11-pool-v7.json").write_text(json.dumps(out, indent=1))
        return 0

    # --- v7 = v6 + ext : recette champion + GxF ---
    EU7 = {k: norm(np.concatenate([du[k], dx[k]]))
           for k in ("E_state", "E_diff", "E_goal")}
    y7 = np.concatenate([y6, yX])
    t7 = np.concatenate([t6, tX])
    camp = np.array(["v6"] * len(rows6) + ["ext"] * len(rowsX))
    maj7 = max(y7.mean(), 1 - y7.mean())
    out["majority_v7"] = float(maj7)
    cd7 = norm(EU7["E_state"] + EU7["E_diff"])
    cg7 = norm(EU7["E_state"] + EU7["E_goal"])
    pred, conf, sco = loao_energy(cd7, cg7, y7, t7)
    out["variants"]["v7_gold"] = report("V7 GOLD uxc", pred, conf, sco, y7, maj7)
    pred, conf, sco = gxf_loao(cd7, cg7, y7, t7)
    out["variants"]["v7_gxf"] = report("V7 GxF λ=1", pred, conf, sco, y7, maj7)

    # --- stratification de la queue (produit : qui habite la haute confiance ?)
    order = np.argsort(-conf)
    m = max(1, int(round(len(y7) * 0.25)))
    top = order[:m]
    k_ext = int((pred[top][camp[top] == "ext"]
                 == y7[top][camp[top] == "ext"]).sum())
    k_v6 = int((pred[top][camp[top] == "v6"]
                == y7[top][camp[top] == "v6"]).sum())
    n_ext = int((camp[top] == "ext").sum())
    n_v6 = int((camp[top] == "v6").sum())
    out["queue_top25"] = {
        "n": m, "ext": {"n": n_ext, "acc": k_ext / max(1, n_ext),
                        "wilson95": wilson(k_ext, n_ext) if n_ext else None},
        "v6": {"n": n_v6, "acc": k_v6 / max(1, n_v6),
               "wilson95": wilson(k_v6, n_v6) if n_v6 else None},
    }
    print(f"queue top-25 % ({m}) : ext {n_ext} acc "
          f"{k_ext / max(1, n_ext):.3f} | v6 {n_v6} acc {k_v6 / max(1, n_v6):.3f}")

    (PILOT / "s11-pool-v7.json").write_text(json.dumps(out, indent=1))
    print(f"\nartefact : {PILOT / 's11-pool-v7.json'}")
    print("RAPPEL : aucune promotion — la règle v2 (AUC>0.864 ET cov>30 %) "
          "tranche à la main de l'owner.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["join", "embed", "eval", "all"],
                    default="all")
    ap.add_argument("--limit", type=int, default=0,
                    help="sonde : n premiers échantillons seulement")
    a = ap.parse_args()
    if a.stage in ("join", "all"):
        stage_join()
    if a.stage in ("embed", "all"):
        stage_embed(limit=a.limit)
    if a.stage in ("eval", "all"):
        return stage_eval()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
