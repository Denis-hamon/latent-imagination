"""Clean Tier assembly (story 4.3, FR-16) — core, zero network (AD-6).

Reads candidate tasks from landing parquets (SWE-smith task set + SWE-bench
verified), applies the pre-registered hardening criteria by IMPORTING
`probe.hardening` (never forked — the envelope's criteria live there), and
resolves per-item licenses from the committed inventory (4.3 Task 0): copyleft
or UNKNOWN → audit queue, never a tier (harvest-policy rights rule).

Floor discipline (FR-16 ladder): kept below 10⁴ → the report declares which
ladder rung held and the shipped artifact carries a header caveat — never a
silent small tier.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from core_schema.errors import SchemaError
from probe.hardening import reject_reasons  # imported, NOT forked (envelope discipline)
from pydantic import BaseModel, ConfigDict

_TASK_HASH = re.compile(r"[0-9a-f]{8,}")


def upstream_repo(task_repo: str) -> str:
    """`swesmith/oauthlib__oauthlib.1fd52536` → `oauthlib/oauthlib` (dots kept);
    plain `astropy/astropy` passes through unchanged."""
    rest = task_repo.split("/", 1)[-1]
    owner, _, remainder = rest.partition("__")
    if not remainder:
        if "/" in task_repo and "." not in rest:
            return task_repo  # plain owner/repo (e.g. SWE-bench Verified rows)
        raise SchemaError("LI-CORPUS-009", "task repo lacks owner__repo shape", {"got": task_repo})
    if not owner:
        raise SchemaError("LI-CORPUS-009", "task repo lacks owner", {"got": task_repo})
    segs = remainder.split(".")
    cut = next((i for i, s in enumerate(segs) if _TASK_HASH.fullmatch(s)), len(segs))
    return f"{owner}/{'.'.join(segs[:cut])}"


def _as_test_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, str) and raw.startswith("["):
        try:
            return [str(t) for t in json.loads(raw)]
        except ValueError as exc:
            raise SchemaError("LI-CORPUS-009", "test list unparseable", {"raw": raw[:80]}) from exc
    return [str(raw)]


def load_inventory(path: Path) -> dict:
    try:
        raw = json.loads(Path(path).read_text())
    except FileNotFoundError as exc:
        raise SchemaError("LI-CORPUS-010", "license inventory missing", {"path": str(path)}) from exc
    except ValueError as exc:
        raise SchemaError("LI-CORPUS-010", "license inventory unparseable", {"path": str(path)}) from exc
    if not isinstance(raw.get("upstream_repos"), dict):
        raise SchemaError("LI-CORPUS-010", "inventory lacks upstream_repos", {})
    return raw


def iter_smith_candidates(parquet_paths: list[Path]) -> list[dict]:
    out: list[dict] = []
    for p in parquet_paths:
        if not Path(p).is_file():
            raise SchemaError("LI-CORPUS-009", "candidate parquet missing", {"path": str(p)})
        t = pq.read_table(p)
        for row in t.to_pylist():
            out.append({
                "instance_id": row["instance_id"],
                "repo": row["repo"],
                "patch": row.get("patch") or "",
                "FAIL_TO_PASS": _as_test_list(row.get("FAIL_TO_PASS")),
                "PASS_TO_PASS": _as_test_list(row.get("PASS_TO_PASS")),
                "problem_statement": row.get("problem_statement") or "",
                "image_name": row.get("image_name"),
                "source": "swe-smith",
            })
    return out


class CleanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    repo: str            # task repo as recorded by the source (e.g. swesmith/…)
    upstream_repo: str   # the real OSS repo (license + exclusion surface)
    license: str
    source: str
    f2p_tests: list[str]
    image_name: str | None
    patch_sha256: str


class FloorVerdict(BaseModel):
    in_band: bool
    kept: int
    rung: str  # none | expand-sources | extend-repos | publish-sub-floor-with-header-caveat
    caveat: str


def evaluate_floor(kept: int, band_min: int, band_max: int, *, sources_exhausted: bool) -> FloorVerdict:
    if band_min <= kept < band_max:
        return FloorVerdict(in_band=True, kept=kept, rung="none", caveat="")
    if kept >= band_max:
        raise SchemaError("LI-CORPUS-009", "above band max — split the tier instead of overflowing", {"kept": kept})
    if not sources_exhausted:
        return FloorVerdict(
            in_band=False, kept=kept, rung="expand-sources",
            caveat=f"SUB-FLOOR ({kept} < {band_min}): declared sources not yet expanded (SWE-Gym/R2E-Gym fetch is the execution-window action).",
        )
    return FloorVerdict(
        in_band=False, kept=kept, rung="publish-sub-floor-with-header-caveat",
        caveat=f"SUB-FLOOR ({kept} < {band_min}): published below the FR-16 floor WITH this header caveat; criteria tour at Epic-4 exit.",
    )


def assemble_clean(candidates: list[dict], inventory: dict, allowlist: list[str]) -> dict:
    kept: list[CleanItem] = []
    rejects: list[dict] = []
    upstream = inventory["upstream_repos"]
    for row in candidates:
        row = dict(row)
        row["FAIL_TO_PASS"] = _as_test_list(row.get("FAIL_TO_PASS"))  # sources disagree on shape
        reasons = reject_reasons(row)  # probe.hardening — the criteria, imported
        up = upstream_repo(row["repo"])
        lic = upstream.get(up, {}).get("license", "UNKNOWN")
        if lic not in allowlist:
            reasons.append(f"license:{lic.lower().replace('.', '-')}")
        if reasons:
            rejects.append({"instance_id": row["instance_id"], "reasons": reasons})
            continue
        kept.append(CleanItem(
            instance_id=row["instance_id"], repo=row["repo"], upstream_repo=up,
            license=lic, source=row["source"], f2p_tests=row["FAIL_TO_PASS"],
            image_name=row.get("image_name"),
            patch_sha256=sha256((row.get("patch") or "").encode()).hexdigest(),
        ))
    by_reason: dict[str, int] = {}
    for r in rejects:
        for reason in r["reasons"]:
            by_reason[reason] = by_reason.get(reason, 0) + 1
    return {"kept": kept, "rejects": rejects, "by_reason": by_reason}


def clean_table(items: list[CleanItem]) -> pa.Table:
    rows = [i.model_dump(mode="json") for i in items]
    schema = pa.schema([
        ("instance_id", pa.string()), ("repo", pa.string()), ("upstream_repo", pa.string()),
        ("license", pa.string()), ("source", pa.string()),
        ("f2p_tests", pa.list_(pa.string())), ("image_name", pa.string()),
        ("patch_sha256", pa.string()),
    ])
    cols = {f: [r[f] for r in rows] for f in schema.names}
    return pa.table(cols, schema=schema)
