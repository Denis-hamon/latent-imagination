"""Clean Tier assembly (story 4.3) — FR-16 floor + license discipline."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from core_schema.errors import SchemaError
from corpus.clean import (
    assemble_clean,
    clean_table,
    evaluate_floor,
    load_inventory,
    upstream_repo,
)
from corpus.clean_emit import emit_clean_tier

D = Path(__file__).resolve().parents[3]
INVENTORY = D / "governance" / "corpus" / "license-inventory-v1.json"
POLICY = D / "governance" / "corpus" / "hardening-policy-v1.toml"

GOOD_PATCH = "diff --git a/pkg/core.py b/pkg/core.py\n--- a/pkg/core.py\n+++ b/pkg/core.py\n@@ -0,0 +1 @@\n+fix\n"
TEST_ONLY = "diff --git a/tests/test_x.py b/tests/test_x.py\n--- a/tests/test_x.py\n+++ b/tests/test_x.py\n@@ -0,0 +1 @@\n+t\n"
INFRA_F2P = ["conftest.py::test_env"]


def _cand(iid: str, repo: str, patch: str = GOOD_PATCH, f2p=None):
    return {"instance_id": iid, "repo": repo, "patch": patch,
            "FAIL_TO_PASS": f2p or ["tests/test_x.py::test_ok"], "PASS_TO_PASS": [],
            "problem_statement": "", "image_name": None, "source": "swe-smith"}


def _write_parquet(tmp_path: Path, rows: list[dict]):
    t = pa.table({k: [r[k] for r in rows] for k in rows[0]})
    p = tmp_path / "train-0.parquet"
    pq.write_table(t, p)
    return p


def test_upstream_repo_parsing():
    assert upstream_repo("swesmith/oauthlib__oauthlib.1fd52536") == "oauthlib/oauthlib"
    assert upstream_repo("swesmith/pdfminer__pdfminer.six.1a8bd2f7") == "pdfminer/pdfminer.six"
    with pytest.raises(SchemaError):
        upstream_repo("garbage")


def test_assembly_rejects_hardening_and_license(tmp_path):
    cands = [
        _cand("a__a-1", "swesmith/mahmoud__boltons.12345678"),          # BSD-2 ok
        _cand("b__b-2", "swesmith/Cog-Creators__Red-DiscordBot.33e0eac7"),  # GPL → audit
        _cand("c__c-3", "swesmith/foo__unknownrepo.abcdef99"),          # UNKNOWN → audit
        _cand("d__d-4", "swesmith/bottlepy__bottle.deaded00", patch=TEST_ONLY),  # hardening
        _cand("e__e-5", "swesmith/bottlepy__bottle.deaded00", f2p=INFRA_F2P),    # infra F2P
    ]
    inv = load_inventory(INVENTORY)
    out = assemble_clean(cands, inv, ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD"])
    assert [i.upstream_repo for i in out["kept"]] == ["mahmoud/boltons"]
    assert out["by_reason"]["license:gpl-3-0"] == 1
    assert out["by_reason"]["license:unknown"] == 1
    assert out["by_reason"]["test-only-patch"] == 1
    assert out["by_reason"]["f2p-infra-config"] == 1


def test_real_smith_subset_assembles(tmp_path):
    from corpus.clean import iter_smith_candidates

    parquet = sorted((D / "data" / "landing" / "swe-smith-tasks" / "raw").glob("*.parquet"))
    assert parquet, "landing scratch missing (scp from node)"
    cands = iter_smith_candidates(parquet)
    out = assemble_clean(cands, load_inventory(INVENTORY),
                         ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD"])
    assert 0 < len(out["rejects"]) < len(cands)
    assert all(i.license != "UNKNOWN" for i in out["kept"])


def test_floor_verdicts():
    in_band = evaluate_floor(12000, 10_000, 100_000, sources_exhausted=False)
    assert in_band.in_band and in_band.rung == "none"
    expand = evaluate_floor(6000, 10_000, 100_000, sources_exhausted=False)
    assert expand.rung == "expand-sources" and "SUB-FLOOR" in expand.caveat
    subfloor = evaluate_floor(6000, 10_000, 100_000, sources_exhausted=True)
    assert subfloor.rung == "publish-sub-floor-with-header-caveat"
    with pytest.raises(SchemaError):
        evaluate_floor(100_001, 10_000, 100_000, sources_exhausted=True)


def test_emit_subfloor_requires_caveat(tmp_path):
    inv = load_inventory(INVENTORY)
    cands = [_cand("a__a-1", "swesmith/mahmoud__boltons.12345678")]
    out = assemble_clean(cands, inv, ["BSD-2-Clause"])
    verdict = evaluate_floor(len(out["kept"]), 10_000, 100_000, sources_exhausted=True)
    manifest = emit_clean_tier(  # noqa: F841 — truth lives in the shipped report
        tmp_path / "store", out["kept"], out["rejects"], out["by_reason"], verdict,
        artifact_version="v0", hardening_policy_path=POLICY,
        license_inventory_path=INVENTORY, candidates_total=len(cands), code_commit="c" * 40,
    )
    report = json.loads((tmp_path / "store" / "canonical" / "clean-tier" / "v0" / "hardening-report.json").read_text())
    assert report["header_caveat"]  # sub-floor caveat IS in the shipped report
    assert report["floor"]["rung"] == "publish-sub-floor-with-header-caveat"

    # without the caveat the emit is refused (LI-CORPUS-009)
    from corpus.clean import FloorVerdict

    bad = FloorVerdict(in_band=False, kept=1, rung="expand-sources", caveat="")
    with pytest.raises(SchemaError) as ei:
        emit_clean_tier(
            tmp_path / "s2", out["kept"], out["rejects"], out["by_reason"], bad,
            artifact_version="v0", hardening_policy_path=POLICY,
            license_inventory_path=INVENTORY, candidates_total=1, code_commit="c" * 40,
        )
    assert ei.value.code == "LI-CORPUS-009"


def test_clean_table_schema():
    from corpus.clean import CleanItem

    item = CleanItem(instance_id="a__a-1", repo="swesmith/x__y.12345678", upstream_repo="x/y",
                     license="MIT", source="swe-smith", f2p_tests=["t"], image_name=None,
                     patch_sha256="a" * 64)
    t = clean_table([item])
    assert t.num_rows == 1 and t.column("f2p_tests")[0].as_py() == ["t"]
