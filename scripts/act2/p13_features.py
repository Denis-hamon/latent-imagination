#!/usr/bin/env python3
"""P13 vague 2 — représentations alternatives (V7 à V10).

Fenêtre `governance/act2/window-p13-scamper-proposal.md`. ZÉRO appel LLM :
encodage local jina-code, même modèle et même cache que `p10_fit.py`.

Trois représentations, toutes DÉTERMINISTES et disclosées :

  `corps`  — le nom du test remplacé par les LIGNES AJOUTÉES du `test_patch` qui
             le concernent. En Python un nom de test est générique ; ce que le
             test vérifie est dans son corps. `test_patch` est présent pour
             154/154 instances de P12.
  `ast`    — le diff normalisé par `ast_norm_diff.normalize_diff` : identifiants
             et chaînes abstraits, structure préservée. Sépare la FORME du
             changement de la texture du dépôt.
  `hunks`  — le diff découpé par `hunk_split.split_patch`, chaque hunk encodé
             séparément. Le cos test↔diff actuel écrase tout le patch en UN
             scalaire ; ici on garde la distribution (max, moyenne, top-3).

Limite déclarée : `corps` n'existe pas pour w46 — les transitions v39 ne portent
pas de `test_patch`. **V8 et V10 n'ont donc PAS de contrôle positif.** C'est une
faiblesse de la vague 2, elle est écrite ici et reportée dans l'artefact.

Usage : .venv/bin/python scripts/act2/p13_features.py --corpus p12
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "act2"))
AP = ROOT / "data" / "landing" / "act2-pilot"
P13 = AP / "night-harvest" / "py-p12" / "p13"
SEL = AP / "night-harvest" / "py-p12" / "p12-selection.json"
TRONC = 8000          # même troncature que `diff_to` dans la convention v39
MAX_HUNKS = 12        # au-delà, on garde les 12 premiers et on le journalise

_DEF = re.compile(r"^\+\s*(?:async\s+)?def\s+([A-Za-z_]\w*)")


def corps_test(test_patch: str, test_id: str) -> tuple[str, str]:
    """Lignes ajoutées du `test_patch` concernant `test_id`. Rend (texte, mode)."""
    from hunk_split import split_sections
    fichier = test_id.split("::")[0]
    fn = test_id.split("::")[-1].split("[")[0]
    ajouts_fichier: list[str] = []
    for sec in split_sections(test_patch):
        _, b = sec.files()
        if b.removeprefix("b/") != fichier:
            continue
        for h in sec.hunks:
            lignes = [l[1:] for l in h.body if l.startswith("+") and not l.startswith("+++")]
            # si le `def` du test est AJOUTÉ par ce hunk, le corps commence là
            deb = next((i for i, l in enumerate(h.body)
                        if (m := _DEF.match(l)) and m.group(1) == fn), None)
            if deb is not None:
                corps = [l[1:] for l in h.body[deb:] if l.startswith("+")]
                return "\n".join(corps)[:TRONC], "def-ajoutee"
            ajouts_fichier += lignes
    if ajouts_fichier:
        return "\n".join(ajouts_fichier)[:TRONC], "ajouts-du-fichier"
    return test_id, "repli-nom-du-test"


def textes(corpus: str) -> dict:
    """Rend les trois familles de textes, alignées sur l'ordre de `p13_metrics.charge`."""
    import p13_metrics as M
    from ast_norm_diff import normalize_diff
    from hunk_split import split_patch

    D = M.charge(corpus)
    tp = {}
    if SEL.is_file():
        sel = json.load(open(SEL))
        sel = sel if isinstance(sel, list) else list(sel.values())[0]
        tp = {i["instance_id"]: i.get("test_patch", "") for i in sel}

    modes: dict[str, int] = {}
    corps, ast, hks = [], [], []
    for k in range(len(D["y"])):
        d, t, inst = D["diff"][k], D["test"][k], D["inst"][k]
        if inst in tp and tp[inst]:
            c, mo = corps_test(tp[inst], t)
        else:
            c, mo = t, "absent-du-corpus"
        modes[mo] = modes.get(mo, 0) + 1
        corps.append(c)
        ast.append(normalize_diff(d)[:TRONC])
        h = [x.text()[:TRONC] for x in split_patch(d)][:MAX_HUNKS]
        hks.append(h if h else [d[:TRONC]])
    print(f"  corps du test — modes d'extraction : {modes}", flush=True)
    n_tronq = sum(1 for x in split_patch_counts(D["diff"]) if x > MAX_HUNKS)
    print(f"  hunks : {sum(len(h) for h in hks)} au total ; "
          f"{n_tronq} diffs tronqués à {MAX_HUNKS} hunks", flush=True)
    return {"D": D, "corps": corps, "ast": ast, "hunks": hks, "modes": modes,
            "n_diffs_tronques": n_tronq}


def split_patch_counts(diffs):
    from hunk_split import split_patch
    return [len(split_patch(d)) for d in diffs]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=("w46", "p12"), default="p12")
    a = ap.parse_args()
    P13.mkdir(parents=True, exist_ok=True)
    import p10_fit as F
    # 4 workers a ~660 Mo ont sature le swap (2 Go/3 Go) et fait tomber
    # l'encodage a 8 textes / 15 min. Reglable, defaut 2.
    F.EMB_WORKERS = int(os.environ.get("P13_EMB_WORKERS", "2"))

    T = textes(a.corpus)
    D = T["D"]

    # --- corps du test et diff AST : un vecteur par ligne, dédoublonné
    for nom, txts in (("corps", T["corps"]), ("ast", T["ast"])):
        cible = P13 / f"_E-{a.corpus}-{nom}.npy"
        if cible.is_file():
            print(f"{nom} : deja sur disque, saute", flush=True)
            continue
        uniq = sorted(set(txts))
        print(f"{nom} : {len(uniq)} textes distincts à encoder", flush=True)
        vec = dict(zip(uniq, F.embed_pool(uniq, nom)))
        np.save(P13 / f"_E-{a.corpus}-{nom}.npy",
                np.stack([vec[t] for t in txts]).astype("float64"))

    # --- hunks : agrégats de cos(test, hunk). Un seul scalaire aujourd'hui,
    #     une distribution ici.
    if (P13 / f"_E-{a.corpus}-hunkagg.npy").is_file():
        print("hunkagg : deja sur disque, saute", flush=True)
        plats = []
    else:
        plats = sorted({h for hs in T["hunks"] for h in hs})
    print(f"hunks : {len(plats)} textes distincts à encoder", flush=True)
    vh = dict(zip(plats, F.embed_pool(plats, "hunks"))) if plats else {}
    Et = np.load(AP / "night-harvest" / "py-p12" / "p10" / f"_X-{a.corpus}.npy",
                 mmap_mode="r")[:, 768:1536]
    agg = np.zeros((len(D["y"]), 5))
    for k, hs in enumerate(T["hunks"] if plats else []):
        c = np.array([float(np.dot(vh[h], Et[k])) for h in hs])
        o = np.sort(c)[::-1]
        agg[k] = [c.max(), c.mean(), o[:3].mean(), c.min(), float(len(c))]
    if plats:
        np.save(P13 / f"_E-{a.corpus}-hunkagg.npy", agg)

    meta = {"corpus": a.corpus, "troncature": TRONC, "max_hunks": MAX_HUNKS,
            "modes_extraction_corps": T["modes"], "n_diffs_tronques": T["n_diffs_tronques"],
            "colonnes_hunkagg": ["cos_max", "cos_moyen", "cos_top3", "cos_min", "n_hunks"],
            "controle_positif_V8_V10": "ABSENT — les transitions v39 (w46) ne "
                                       "portent pas de test_patch"}
    (P13 / f"features-{a.corpus}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"\nécrit : {P13}/_E-{a.corpus}-{{corps,ast,hunkagg}}.npy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
