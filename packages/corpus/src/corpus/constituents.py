"""Eval constituents assembly (story 4.2, Task 0) — pure, no network.

The Noisy Tier must never train on the measurement's own test set (FR-15
disjointness / R11). The exclusion set is derived ONLY from sealed surfaces:
governance/probe-design split manifests + the clean-slice items. The output
(`governance/corpus/eval-constituents-v1.json`) is small enough to commit.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError


def instance_repo(instance_id: str) -> str:
    """Repo of an eval instance, both sealed shapes:

    - SWE-bench: ``django__django-16379`` / ``scikit-learn__scikit-learn-25931``
      → ``owner/repo`` (issue-number suffix split off the LAST dash).
    - SWE-smith: ``mahmoud__boltons.3bfcfdd0.lm_rewrite__or6ab7bk`` or the probe
      matrix form ``smith::PyCQA__flake8.cf1542ce.combine_file__4w2x9qv4::model::0``
      → the ``owner__repo`` prefix before the first ``.`` segment.
    """
    raw = instance_id
    s = raw
    if "::" in s:  # probe-matrix form: smith::<id>::<model>::<n>
        parts = s.split("::")
        s = parts[1] if len(parts) > 1 else s
    core = s.split(".", 1)[0]  # drop SWE-smith task suffix segments
    if "__" not in core:
        raise SchemaError("LI-CORPUS-007", "instance id has no owner__repo prefix", {"id": raw})
    owner, _, repo = core.partition("__")
    if "-" in repo:  # SWE-bench issue-number suffix
        repo = repo.rsplit("-", 1)[0]
    if not owner or not repo:
        raise SchemaError("LI-CORPUS-007", "instance id repo/owner empty", {"id": raw})
    return f"{owner}/{repo}"


def _sha256(path: Path) -> str:
    try:
        return sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError as exc:  # no silent empty constituents (4.1 review rule)
        raise SchemaError("LI-CORPUS-007", "constituent source missing", {"path": str(path)}) from exc


def build_constituents(probe_design_dir: Path, out_path: Path, *, version: int = 1) -> dict:
    """Assemble eval-constituents-vN.json from the sealed probe surfaces."""
    d = Path(probe_design_dir)
    sources = []
    instance_ids: set[str] = set()
    repos: set[str] = set()
    for name in ("split-manifest.json", "matched-split-manifest.json"):
        f = d / name
        manifest = json.loads(f.read_text())  # decode error = loud (sealed file)
        sources.append({"file": str(f), "sha256": _sha256(f)})
        for iid in manifest["eval_instance_ids"]:
            instance_ids.add(iid)
            repos.add(instance_repo(iid))
        repos.update(manifest.get("eval_repos", []))
    slice_items = json.loads((d / "clean-slice" / "items.json").read_text())
    sources.append({"file": str(d / "clean-slice" / "items.json"), "sha256": _sha256(d / "clean-slice" / "items.json")})
    for item in slice_items:
        iid = item.get("instance_id")
        if iid:
            instance_ids.add(iid)
            repos.add(instance_repo(iid))
        if item.get("repo"):
            repos.add(item["repo"])
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
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(out_path)
    return payload


def load_constituents(path: Path) -> dict:
    try:
        raw = json.loads(Path(path).read_text())
    except FileNotFoundError as exc:
        raise SchemaError("LI-CORPUS-007", "constituents file missing", {"path": str(path)}) from exc
    except ValueError as exc:
        raise SchemaError("LI-CORPUS-007", "constituents file unparseable", {"path": str(path)}) from exc
    for key in ("instance_ids", "repos", "prs"):
        if key not in raw:
            raise SchemaError("LI-CORPUS-007", f"constituents missing '{key}'", {"path": str(path)})
    return raw


def repo_set(constituents: dict) -> set[str]:
    """The conservative surface: declared repos PLUS every instance's repo."""
    out = set(constituents["repos"])
    for iid in constituents["instance_ids"]:
        out.add(instance_repo(iid))
    return out


def task_keys(constituents: dict) -> frozenset[str]:
    return frozenset(constituents["instance_ids"])


def pr_keys(constituents: dict) -> frozenset[str]:
    return frozenset(str(p) for p in constituents["prs"])
