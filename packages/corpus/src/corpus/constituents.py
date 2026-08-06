"""Eval constituents assembly (story 4.2, Task 0) — pure, no network.

The Noisy Tier must never train on the measurement's own test set (FR-15
disjointness / R11). The exclusion set is derived ONLY from sealed surfaces:
governance/probe-design split manifests + the clean-slice items. The output
(`governance/corpus/eval-constituents-v1.json`) is small enough to commit.

Review fixes folded in: relative source paths (CWD-independent rebuilds), typed
loading (fail-closed), coded errors end-to-end, case-folded repo identity.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError

_TASK_HASH = re.compile(r"[0-9a-f]{8,}")  # SWE-smith task-hash segment


def norm_repo(repo: str) -> str:
    """GitHub repo identity is case-insensitive; comparisons are folded (CR 4.2)."""
    return repo.strip().casefold()


def instance_repo(instance_id: str) -> str:
    """Repo of an eval instance, all sealed shapes:

    - SWE-bench: ``django__django-16379`` / ``scikit-learn__scikit-learn-25931``
      → ``owner/repo`` (issue-number suffix = trailing dash + digits).
    - SWE-smith: ``mahmoud__boltons.3bfcfdd0.lm_rewrite__or6ab7bk`` or the probe
      form ``smith::PyCQA__flake8.cf1542ce.combine_file__4w2x9qv4::model::0``
      → ``owner/__ + everything before the task-hash segment``. Dots INSIDE a
      repo name (``chart.js``) are preserved: the split stops at the 8+-hex
      task segment, never at the first dot (CR 4.2 fix).
    """
    raw = instance_id
    s = raw.split("::")[1] if raw.split("::")[0] in ("smith", "verified") and len(raw.split("::")) > 1 else raw
    owner, sep, rest = s.partition("__")
    if not sep or not owner or not rest:
        raise SchemaError("LI-CORPUS-007", "instance id has no owner__repo prefix", {"id": raw})
    segs = rest.split(".")
    cut = next((i for i, seg in enumerate(segs) if _TASK_HASH.fullmatch(seg)), len(segs))
    repo = ".".join(segs[:cut])
    tail, _, digits = repo.rpartition("-")
    if tail and digits.isdigit():  # SWE-bench issue-number suffix
        repo = tail
    if not repo:
        raise SchemaError("LI-CORPUS-007", "instance id repo empty", {"id": raw})
    return f"{owner}/{repo}"


def _sha256(path: Path) -> str:
    try:
        return sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError as exc:  # no silent empty constituents (4.1 review rule)
        raise SchemaError("LI-CORPUS-007", "constituent source missing", {"path": str(path)}) from exc


def _read_json(path: Path) -> object:
    try:
        return json.loads(_sha256(path) and Path(path).read_text())
    except FileNotFoundError as exc:
        raise SchemaError("LI-CORPUS-007", "constituent source missing", {"path": str(path)}) from exc
    except ValueError as exc:
        raise SchemaError("LI-CORPUS-007", "constituent source unparseable", {"path": str(path)}) from exc


def build_constituents(probe_design_dir: Path, out_path: Path, *, version: int = 1) -> dict:
    """Assemble eval-constituents-vN.json from the sealed probe surfaces.

    Sources are recorded RELATIVE to the repo root so byte-identical rebuilds
    (and the rule's hash citation) survive any invocation CWD (CR 4.2)."""
    d = Path(probe_design_dir).resolve()
    repo_root = d.parent.parent  # governance/probe-design → repo root
    sources = []
    instance_ids: set[str] = set()
    repos: set[str] = set()
    for name in ("split-manifest.json", "matched-split-manifest.json"):
        f = d / name
        manifest = _read_json(f)
        if not isinstance(manifest, dict) or "eval_instance_ids" not in manifest:
            raise SchemaError("LI-CORPUS-007", "split manifest lacks eval_instance_ids", {"file": str(f)})
        sources.append({"file": str(f.relative_to(repo_root)), "sha256": _sha256(f)})
        for iid in manifest["eval_instance_ids"]:
            instance_ids.add(iid)
            repos.add(instance_repo(iid))
        repos.update(manifest.get("eval_repos", []))
    slice_path = d / "clean-slice" / "items.json"
    slice_items = _read_json(slice_path)
    if not isinstance(slice_items, list):
        raise SchemaError("LI-CORPUS-007", "clean-slice items not a list", {"file": str(slice_path)})
    sources.append({"file": str(slice_path.relative_to(repo_root)), "sha256": _sha256(slice_path)})
    for item in slice_items:
        if not isinstance(item, dict):
            raise SchemaError("LI-CORPUS-007", "clean-slice item not a mapping", {})
        iid = item.get("instance_id")
        if iid:
            instance_ids.add(iid)
            repos.add(instance_repo(iid))
        if item.get("repo"):
            repos.add(str(item["repo"]))
    if not instance_ids or not repos:
        raise SchemaError("LI-CORPUS-007", "constituents would be EMPTY — refusing", {})
    payload = {
        "version": version,
        "sources": sources,
        "instance_ids": sorted(instance_ids),
        "repos": sorted(repos),
        "prs": [],
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(out_path)
    return payload


def load_constituents(path: Path) -> dict:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise SchemaError("LI-CORPUS-007", "constituents root not a mapping", {"path": str(path)})
    for key in ("instance_ids", "repos", "prs"):
        value = raw.get(key)
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise SchemaError(
                "LI-CORPUS-007", f"constituents '{key}' must be a list of strings (fail-closed)",
                {"path": str(path)},
            )
    return raw


def repo_set(constituents: dict) -> frozenset[str]:
    """Folded conservative surface: declared repos PLUS every instance's repo."""
    out = {norm_repo(r) for r in constituents["repos"]}
    for iid in constituents["instance_ids"]:
        out.add(norm_repo(instance_repo(iid)))
    return frozenset(out)


def pr_keys(constituents: dict) -> frozenset[str]:
    return frozenset(str(p) for p in constituents["prs"])
