#!/usr/bin/env python3
"""Découpeur de hunks unifié — harnais partagé v49 (E3) / v48 amendée.

Modèle : un patch = suite de SECTIONS de fichier. Chaque section a un en-tête
(`diff --git` + attributs : index/mode/---/+++ OU marqueur binaire) et zéro ou
plusieurs hunks. Parsing PAR DÉCOMPTE @@ (robuste aux lignes de corps qui
ressemblent à des en-têtes) ; les lignes « \\ No newline at end of file » sont
rattachées au hunk sans compter dans les totaux.

API :
  split_sections(patch) -> list[FileSection]
  split_patch(patch)    -> list[Hunk]            (hunks aplatis, ordre du patch)
  remove_hunks(patch, drop) -> str               (drop = indices GLOBAUX de hunks)
  hunk_summary(patch)   -> list[dict]

Reconstruction fidèle : remove_hunks(patch, set()) == patch à l'octet près.
Une section TEXTE dont tous les hunks sont retirés est supprimée (diff vide) ;
une section BINAIRE (sans hunk) est toujours conservée.

Zéro dépendance hors stdlib. Auto-tests : uv run python scripts/act2/hunk_split.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class Hunk:
    header: str = ""
    body: list[str] = field(default_factory=list)

    def text(self) -> str:
        return self.header + "".join(self.body)


@dataclass
class FileSection:
    header: list[str] = field(default_factory=list)  # diff --git + attributs
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def is_binary(self) -> bool:
        return not self.hunks and any(l.startswith("Binary files ") for l in self.header)

    def files(self) -> tuple[str, str]:
        a = b = ""
        for l in self.header:
            if l.startswith("--- "):
                a = l[4:].split("\t")[0].strip()
            elif l.startswith("+++ "):
                b = l[4:].split("\t")[0].strip()
        return a, b


def split_sections(patch: str) -> list[FileSection]:
    lines = patch.splitlines(keepends=True)
    secs: list[FileSection] = []
    cur: FileSection | None = None
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if ln.startswith("diff --git "):
            cur = FileSection(header=[ln])
            secs.append(cur)
            i += 1
            while i < n and not lines[i].startswith("@@") and not lines[i].startswith("diff --git "):
                cur.header.append(lines[i])
                i += 1
            continue
        m = _HUNK_RE.match(ln)
        if m and cur is not None:
            old_cnt = int(m.group(2)) if m.group(2) is not None else 1
            new_cnt = int(m.group(4)) if m.group(4) is not None else 1
            h = Hunk(header=ln, body=[])
            i += 1
            o = nw = 0
            while i < n:
                b = lines[i]
                if b.startswith("diff --git "):
                    break
                if b.startswith("\\"):
                    h.body.append(b)      # marqueur no-newline, ne compte pas
                    i += 1
                    continue
                if o >= old_cnt and nw >= new_cnt:
                    break
                h.body.append(b)
                if b.startswith(" ") or b.startswith("-"):
                    o += 1
                    if b.startswith(" "):
                        nw += 1
                elif b.startswith("+"):
                    nw += 1
                i += 1
            cur.hunks.append(h)
            continue
        i += 1  # préambule avant le premier diff --git
    return secs


def split_patch(patch: str) -> list[Hunk]:
    return [h for s in split_sections(patch) for h in s.hunks]


def remove_hunks(patch: str, drop: set[int]) -> str:
    """Reconstruit le patch sans les hunks d'indices globaux `drop`.
    Section texte vidée de ses hunks -> supprimée ; section binaire ou sans
    hunk (mode-only) -> conservée telle quelle."""
    out: list[str] = []
    k = 0
    for s in split_sections(patch):
        keep = []
        for h in s.hunks:
            if k not in drop:
                keep.append(h)
            k += 1
        if keep or not s.hunks:
            out.extend(s.header)
            out.extend(h.text() for h in keep)
    return "".join(out)


def hunk_summary(patch: str) -> list[dict]:
    res = []
    k = 0
    for s in split_sections(patch):
        for h in s.hunks:
            body = h.body
            res.append({"idx": k, "files": s.files(),
                        "old": len([l for l in body if l.startswith((" ", "-"))]),
                        "new": len([l for l in body if l.startswith((" ", "+"))])})
            k += 1
    return res


def _reverse_hunk_header(header: str) -> str:
    m = re.match(r"^@@ -(\d+(?:,\d+)?) \+(\d+(?:,\d+)?) @@(.*)$", header.rstrip("\n"))
    if not m:
        return header
    return f"@@ -{m.group(2)} +{m.group(1)} @@{m.group(3)}\n"


def reverse_patch(patch: str) -> str:
    """Inverse un patch unifié : équivalent textuel de `git apply -R`.

    Échange old/new (les rôles des lignes `---`/`+++`), inverse les signes des
    lignes de corps et transpose les comptes `@@`. Les lignes `index`/modes sont
    retirées (git apply ne les exige pas et leurs hashes ne correspondraient
    plus). Les sections sans hunk (binaires) sont conservées telles quelles.
    Vérifié empiriquement : appliquer `reverse_patch(bug)` en AVANT sur l'arbre
    bogué redonne l'état propre (validé v48, 2026-08-22, pandas 100 failed→100
    passed)."""
    out: list[str] = []
    for sec in split_sections(patch):
        if not sec.hunks:
            out.extend(sec.header)
            continue
        old_path = new_path = None
        gitline = None
        for l in sec.header:
            if l.startswith("diff --git"):
                gitline = l
            elif l.startswith("--- "):
                old_path = l[4:].strip()
            elif l.startswith("+++ "):
                new_path = l[4:].strip()
        if gitline:
            out.append(gitline)
        # rôles inversés : l'ancien devient le nouveau et réciproquement
        if new_path is not None:
            out.append("--- " + new_path + "\n")
        if old_path is not None:
            out.append("+++ " + old_path + "\n")
        for h in sec.hunks:
            out.append(_reverse_hunk_header(h.header))
            for bl in h.body:
                if bl.startswith("+"):
                    out.append("-" + bl[1:])
                elif bl.startswith("-"):
                    out.append("+" + bl[1:])
                else:
                    out.append(bl)  # contexte ou « \ No newline »
    return "".join(out)


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[2]

    def check(patch: str) -> tuple[bool, str]:
        secs = split_sections(patch)
        n_h = sum(len(s.hunks) for s in secs)
        rt = remove_hunks(patch, set()) == patch
        rm = all(len(split_patch(remove_hunks(patch, {k}))) == n_h - 1 for k in range(n_h))
        return rt and rm, f"hunks={n_h} roundtrip={'OK' if rt else 'ÉCHEC'} remove={'OK' if rm else 'ÉCHEC'}"

    total = ok = 0
    tix = json.loads((ROOT / "data/landing/act2-pilot/mswb/mswb-tickets.json").read_text())
    vset = set()
    for repo in ("vuejs__core", "iamkun__dayjs"):
        f = ROOT / "data/landing/act2-pilot/mswb" / repo / "verified-mswb.json"
        if f.is_file():
            vset |= {x["issue"] for x in json.loads(f.read_text()) if isinstance(x, dict) and x.get("ok")}
    for t in tix:
        if t["issue"] in vset and len(re.findall(r"(?m)^@@", t["fix_patch"])) >= 2:
            total += 1
            good, msg = check(t["fix_patch"])
            ok += good
            if not good:
                print("ÉCHEC", t["issue"], msg)
    print(f"mswb verified multi-hunks : {ok}/{total} roundtrip+remove OK")
    sel_f = ROOT / "data/landing/act2-pilot/w48/selection-coherente.json"
    if sel_f.is_file():
        sel = json.loads(sel_f.read_text())["selection"]
        t2 = o2 = 0
        for s in sel:
            if len(re.findall(r"(?m)^@@", s["fix_patch"])) >= 2:
                t2 += 1
                good, _ = check(s["fix_patch"])
                o2 += good
        print(f"swe-smith sélection complète multi-hunks : {o2}/{t2} OK")
    sys.exit(0 if ok == total else 1)
