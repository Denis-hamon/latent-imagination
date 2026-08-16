#!/usr/bin/env python3
"""Story 13.2 — normalisation AST des diffs : abstraction des identifiants,
chaînes et commentaires, structure préservée. Objectif : que la géométrie voie
« la forme du changement », pas la texture du repo (noms propres au projet).

Recette DÉTERMINISTE, stdlib seule (module tokenize), disclosée dans l'artefact :
  - tokens NAME non-mots-clés → v_k (k = rang d'apparition du nom DISTINCT dans
    le diff entier ; la même table de renommage couvre les lignes - et + pour
    que l'alignement survive) ; self/cls conservés (structure, pas texture) ;
  - littéraux chaîne → '"S"' ; commentaires supprimés ;
  - headers abstraits : chemins → PATH, index → HASH, contexte du hunk @@
    (nom de classe) supprimé — les numéros de lignes restent (structure) ;
  - nombres et mots-clés conservés (recette conservatrice : un nombre peut
    porter le sens du fix — on n'abstrait pas ce qu'on ne sait pas être de la
    texture) ;
  - ligne non tokenisable (snippet tronqué, langage non-Python) → fallback
    regex identique (identifiants → v_k avec la même table, mots-clés Py+Go
    préservés), jamais crash.

0 appel. Sortie : data/landing/act2-pilot/genfam… non — sortie :
`<pool>-astdiff-diffs.jsonl` (une ligne {task, norm_diff} par row du pool).
Run: uv run python scripts/act2/ast_norm_diff.py --pool v10
"""
from __future__ import annotations

import argparse
import io
import json
import keyword
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
GO_WORDS = {"func", "return", "if", "else", "for", "range", "nil", "true",
            "false", "var", "const", "import", "package", "string", "int",
            "error", "map", "make", "len", "append"}
KEEP = set(keyword.kwlist) | GO_WORDS | {"self", "cls"}  # self/cls : structure
# Python transversale, pas de la texture de repo (recette conservatrice)
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _norm_line(line: str, table: dict[str, str]) -> str:
    def canon(name: str) -> str:
        if name in KEEP:
            return name
        if name not in table:
            table[name] = f"v{len(table)}"
        return table[name]
    try:
        out = []
        for tok in tokenize.generate_tokens(io.StringIO(line).readline):
            if tok.type == tokenize.NAME:
                out.append(canon(tok.string))
            elif tok.type == tokenize.STRING:
                out.append('"S"')
            elif tok.type == tokenize.COMMENT:
                continue
            else:
                out.append(tok.string)
        return " ".join(out).strip()
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        # fallback regex : mêmes règles, moindre fidélité structurelle
        def repl(m: re.Match) -> str:
            return canon(m.group(0))
        txt = re.sub(r'#.*$', '', line)
        txt = re.sub(r'"[^"]*"|\'[^\']*\'', '"S"', txt)
        return " ".join(IDENT.sub(repl, txt).split())


def normalize_diff(diff: str) -> str:
    """Table de renommage UNIQUE par diff (les lignes - et + partagent la même
    correspondance nom → v_k : l'alignement du patch survit à l'abstraction)."""
    table: dict[str, str] = {}
    out = []
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            out.append("diff --git a/PATH b/PATH")  # chemins = texture repo
        elif line.startswith(("+++ ", "--- ")):
            out.append(line[:6] + "PATH")
        elif line.startswith("index "):
            out.append("index HASH")
        elif line.startswith("@@"):
            # numéros de lignes conservés (structure), contexte de classe
            # après le second @@ = texture → supprimé
            m = re.match(r"(@@ -?\d+,?\d* \+?\d+,?\d* @@)", line)
            out.append(m.group(1) if m else "@@")
        elif line[:1] in ("+", "-", " "):
            out.append(line[:1] + _norm_line(line[1:], table))
        else:
            out.append(_norm_line(line, table))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="v10")
    args = ap.parse_args()
    rows = json.loads((PILOT / f"latent-pool-{args.pool}.json").read_text())
    out = PILOT / f"latent-pool-{args.pool}-astdiff-diffs.jsonl"
    with out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps({"task": r["task"],
                                 "norm_diff": normalize_diff(r["diff"])}) + "\n")
    print(f"{len(rows)} diffs normalisés → {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
