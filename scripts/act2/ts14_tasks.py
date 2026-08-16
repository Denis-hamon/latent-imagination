#!/usr/bin/env python3
"""Story 14.3 — construction des tâches mutantes TS (window coverage-ts-v1).

Générateur table-driven répliquant le protocole swe-smith : chaque mutation
candidate est VÉRIFIÉE par exécution réelle avant d'entrer au manifeste —
baseline verte → bug appliqué → tests vitest NOMMÉS échouent (F2P) → les autres
restent verts (P2P) → le gold (reverse) reverdit. Un candidat qui ne casse
rien, ou dont la restauration ne reverdit pas, est ÉCARTÉ et journalisé dans
discarded.jsonl (divulgation, jamais de tâche inventée).

Run: uv run python scripts/act2/ts14_tasks.py [--repo <worktree acre>]
Sortie: data/landing/act2-pilot/ts14-pilot/ts14-tasks.json + discarded.jsonl
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "landing" / "act2-pilot" / "ts14-pilot"
DEFAULT_REPO = Path.home() / "Acre" / "worktrees" / "wt-20-13"
PKG = "packages/blocks"

# ---- table de mutations candidates (opérateurs classe swe-smith, TS) ----
MUTATIONS = [
    {
        "task_id": "acre__blocks.diff3-merge.apply_resolutions_swap",
        "target": f"{PKG}/src/merge/diff3-merge.ts",
        "test": "src/merge/__tests__/diff3-merge.test.ts",
        "old": ('    if (resolution.choice === "ours") {\n'
                "      out.push(...segment.oursLines);"),
        "new": ('    if (resolution.choice === "ours") {\n'
                "      out.push(...segment.theirsLines);"),
        "old2": ('    } else if (resolution.choice === "theirs") {\n'
                 "      out.push(...segment.theirsLines);"),
        "new2": ('    } else if (resolution.choice === "theirs") {\n'
                 "      out.push(...segment.oursLines);"),
        "problem": "applyResolutions retourne le texte du mauvais côté lors de "
                   "la résolution ours/theirs d'un conflit de fusion 3-way.",
    },
    {
        "task_id": "acre__blocks.diff3-merge.has_unresolved_inverted",
        "target": f"{PKG}/src/merge/diff3-merge.ts",
        "test": "src/merge/__tests__/diff3-merge.test.ts",
        "old": 'return segments.some((s, i) => s.kind !== "clean" && !resolvedIndices.has(i));',
        "new": 'return segments.some((s, i) => s.kind === "clean" && !resolvedIndices.has(i));',
        "problem": "hasUnresolvedSegments signale des segments à résoudre sur les "
                   "mauvais segments (clean au lieu de conflict).",
    },
    {
        "task_id": "acre__blocks.frontmatter.known_keys_inverted",
        "target": f"{PKG}/src/renderers/frontmatter.ts",
        "test": "src/renderers/__tests__/frontmatter.test.ts",
        "old": "      if (KNOWN_KEYS.has(key)) continue;",
        "new": "      if (!KNOWN_KEYS.has(key)) continue;",
        "problem": "buildFrontmatterYaml laisse passer les clés connues depuis "
                   "extra et ignore les inconnues — inversion de la priorité.",
    },
    {
        "task_id": "acre__blocks.frontmatter.tags_boundary",
        "target": f"{PKG}/src/renderers/frontmatter.ts",
        "test": "src/renderers/__tests__/frontmatter.test.ts",
        "old": "if (meta.tags !== undefined && meta.tags.length > 0) merged.tags = meta.tags;",
        "new": "if (meta.tags !== undefined && meta.tags.length > 1) merged.tags = meta.tags;",
        "problem": "Un tableau tags à UNE entrée disparaît du frontmatter "
                   "(off-by-one sur la borne).",
    },
    {
        "task_id": "acre__blocks.wikilinks.embed_link_swap",
        "target": f"{PKG}/src/renderers/import/obsidian-wikilinks.ts",
        "test": "src/renderers/import/obsidian-wikilinks.test.ts",
        "old": ("      return `![${linkText}](obsidian-embed:${cleanTarget})`;\n"
                "    } else {\n"
                "      // [[target]] → [target](obsidian-wikilink:target)\n"
                "      return `[${linkText}](obsidian-wikilink:${cleanTarget})`;"),
        "new": ("      return `![${linkText}](obsidian-wikilink:${cleanTarget})`;\n"
                "    } else {\n"
                "      // [[target]] → [target](obsidian-wikilink:target)\n"
                "      return `[${linkText}](obsidian-embed:${cleanTarget})`;"),
        "problem": "preprocessWikilinks échange les préfixes URL des liens "
                   "embed et normaux (obsidian-embed ↔ obsidian-wikilink).",
    },
    {
        "task_id": "acre__blocks.wikilinks.fragment_kept",
        "target": f"{PKG}/src/renderers/import/obsidian-wikilinks.ts",
        "test": "src/renderers/import/obsidian-wikilinks.test.ts",
        "old": 'const cleanTarget = target.split("#")[0] ?? target;',
        "new": "const cleanTarget = target;",
        "problem": "Le fragment d'ancre (#heading) n'est plus retiré de la "
                   "cible du wikilink — la cible pointe vers une ancre inexistante.",
    },
    {
        "task_id": "acre__blocks.wikilinks.extract_prefix_swap",
        "target": f"{PKG}/src/renderers/import/obsidian-wikilinks.ts",
        "test": "src/renderers/import/obsidian-wikilinks.test.ts",
        "old": ('const embedMatch = url.match(/^obsidian-embed:(.+)$/);\n'
                "  if (embedMatch) {\n"
                "    return embedMatch[1] ?? null;\n"
                "  }\n"
                "  const linkMatch = url.match(/^obsidian-wikilink:(.+)$/);"),
        "new": ('const embedMatch = url.match(/^obsidian-wikilink:(.+)$/);\n'
                "  if (embedMatch) {\n"
                "    return embedMatch[1] ?? null;\n"
                "  }\n"
                "  const linkMatch = url.match(/^obsidian-embed:(.+)$/);"),
        "problem": "extractWikilinkTarget échange les préfixes attendus : une "
                   "URL embed est lue comme lien et réciproquement (cible fausse).",
    },
    {
        "task_id": "acre__blocks.block-diff.kind_inverted",
        "target": f"{PKG}/src/diff/block-diff.ts",
        "test": "src/diff/__tests__/block-diff.test.ts",
        "old": ('entries.push(matchedAfterIdx.has(j) ? { kind: "unchanged", block }'
                " : modifiedOrAdded.get(block)!);"),
        "new": ('entries.push(!matchedAfterIdx.has(j) ? { kind: "unchanged", block }'
                " : modifiedOrAdded.get(block)!);"),
        "problem": "diffBlocks marque les blocs modifiés comme unchanged et "
                   "réciproquement (condition inversée sur l'appariement).",
    },
    {
        "task_id": "acre__blocks.block-diff.wrong_matched_set",
        "target": f"{PKG}/src/diff/block-diff.ts",
        "test": "src/diff/__tests__/block-diff.test.ts",
        "old": "      if (matchedAfterIdx.has(j)) continue;",
        "new": "      if (matchedBeforeIdx.has(j)) continue;",
        "problem": "Le passage greedy d'appariement consulte le mauvais ensemble "
                   "d'indices (before au lieu de after) — double-appariements.",
    },
    {
        "task_id": "acre__blocks.md-mapping.toggle_collapsed_inverted",
        "target": f"{PKG}/src/renderers/markdown-mapping.ts",
        "test": "src/renderers/__tests__/markdown-roundtrip.test.ts",
        "old": 'const collapsed = toggleMatch[1] === "true";',
        "new": 'const collapsed = toggleMatch[1] !== "true";',
        "problem": "L'état collapsed des toggles importées est inversé "
                   "(ouvert devient fermé et réciproquement).",
    },
    {
        "task_id": "acre__blocks.md-mapping.callout_wrong_node",
        "target": f"{PKG}/src/renderers/markdown-mapping.ts",
        "test": "src/renderers/__tests__/markdown-roundtrip.test.ts",
        "old": 'if (next && next.type === "blockquote") {\n'
               "          const { content, children } = blockquoteToContent(next);",
        "new": 'if (next && next.type === "paragraph") {\n'
               "          const { content, children } = blockquoteToContent(next);",
        "problem": "L'import des callouts cherche un paragraphe au lieu d'un "
                   "blockquote — le contenu des callouts disparaît.",
    },
]


def sh(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          check=False, timeout=timeout)


def vitest(repo: Path, test: str) -> tuple[bool, list[str], list[str], str]:
    r = sh(["node_modules/.bin/vitest", "run", test, "--reporter=json"],
           cwd=repo / PKG, timeout=900)
    raw = r.stdout + r.stderr
    failed, passed = [], []
    try:
        start = raw.find("{")
        data = json.loads(raw[start:raw.rfind("}") + 1])
        for tr in data.get("testResults", []):
            for ar in tr.get("assertionResults", []):
                name = " > ".join(ar.get("ancestorTitles", [])) + " > " + ar.get("title", "")
                (failed if ar.get("status") == "failed" else passed).append(name)
    except (json.JSONDecodeError, ValueError):
        pass
    if r.returncode != 0 and not failed:
        failed = ["<SUITE-ERROR: vitest a échoué sans assertion nominale>"]
    return len(failed) == 0, failed, passed, raw[-500:]


def _diff(repo: Path, rel: str, old: str, new: str) -> str:
    p = repo / rel
    p.write_text(new)
    d = sh(["git", "diff", "--", rel], cwd=repo).stdout
    p.write_text(old)
    return d


def validate(repo: Path, m: dict) -> dict:
    src = repo / m["target"]
    orig = src.read_text()
    if m["old"] not in orig or (m.get("old2") and m["old2"] not in orig):
        return {"task_id": m["task_id"], "rejected": "texte cible introuvable"}
    bug = orig.replace(m["old"], m["new"], 1)
    if m.get("old2"):
        bug = bug.replace(m["old2"], m["new2"], 1)
    patch = _diff(repo, m["target"], orig, bug)
    if not patch:
        return {"task_id": m["task_id"], "rejected": "diff vide"}
    src.write_text(bug)
    try:
        green, failed, passed, raw = vitest(repo, m["test"])
        if green or not failed:
            return {"task_id": m["task_id"],
                    "rejected": "le bug ne casse aucun test nommé",
                    "raw_tail": raw}
        f2p, p2p = sorted(failed), sorted(passed)
        src.write_text(orig)  # gold = restauration exacte
        green2, failed2, _, raw2 = vitest(repo, m["test"])
        if not green2:
            return {"task_id": m["task_id"],
                    "rejected": "la restauration ne reverdit pas (gold invalide)",
                    "still_failing": failed2, "raw_tail": raw2}
        return {"task_id": m["task_id"], "ok": True, "patch": patch,
                "buggy": bug, "f2p": f2p, "p2p": p2p, "problem": m["problem"],
                "target": m["target"], "test": m["test"]}
    finally:
        src.write_text(orig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(DEFAULT_REPO))
    args = ap.parse_args()
    repo = Path(args.repo)
    if sh(["git", "status", "--porcelain"], cwd=repo).stdout.strip():
        print("ABORT: worktree non propre (pré-condition)")
        return 2
    print("baseline verte exigée sur chaque fichier de test candidat…", flush=True)
    for m in MUTATIONS:
        g, f, _, _ = vitest(repo, m["test"])
        if not g:
            print(f"ABORT: baseline cassée pour {m['test']} ({len(f)} échecs)")
            return 3

    tasks, discarded = [], []
    for m in MUTATIONS:
        print(f"validation {m['task_id']} …", flush=True)
        r = validate(repo, m)
        if r.pop("ok", False):
            buggy_f = OUT_DIR / (r["task_id"].replace("/", "_") + ".buggy.py")
            buggy_f.write_text(r["buggy"])  # convention nom .buggy.py (pilot_run)
            tasks.append({
                "instance_id": r["task_id"],
                "repo": "acre/blocks", "lang": "typescript",
                "test_runner": "vitest",
                "target": r["target"], "test": r["test"],
                "patch": r["patch"], "gold": r["patch"],
                "buggy_sha256": __import__("hashlib").sha256(
                    r["buggy"].encode()).hexdigest(),
                "f2p": r["f2p"], "p2p": r["p2p"], "problem": r["problem"],
                "campaign": "coverage-ts-1", "window": "coverage-ts-v1",
            })
            print(f"  OK : {len(r['f2p'])} F2P, {len(r['p2p'])} P2P, gold reverdit")
        else:
            discarded.append({**r, "discarded_at":
                              datetime.now(UTC).isoformat().replace("+00:00", "Z")})
            print(f"  ÉCARTÉ : {r.get('rejected')}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"window": "coverage-ts-v1", "envelope_calls_cap": 80,
                "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "n_tasks": len(tasks), "tasks": tasks}
    (OUT_DIR / "ts14-tasks.json").write_text(json.dumps(manifest, indent=1) + "\n")
    with (OUT_DIR / "discarded.jsonl").open("w") as fh:  # rapport par run, déterministe
        for d in discarded:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    clean = sh(["git", "status", "--porcelain"], cwd=repo).stdout.strip()
    print(f"\nmanifeste : {len(tasks)} tâches validées / {len(MUTATIONS)} candidates "
          f"({len(discarded)} écartées et journalisées) ; worktree final : "
          f"{'PROPRE' if not clean else 'NON PROPRE — ' + clean[:120]}")
    if len(tasks) < 10:
        print(f"NOTE SHORTFALL : quota gelé = 10 tâches ; {10 - len(tasks)} manquantes "
              f"→ disclosure à l'exécution (un quota est un plafond, l'honnêteté d'abord)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
