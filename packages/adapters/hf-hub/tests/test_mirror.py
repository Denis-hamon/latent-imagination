"""HF Hub mirror (story 2.6 task 4 close) — fake hub, zero network."""

from __future__ import annotations

import pytest
from core_schema.errors import SchemaError
from hf_hub_push.mirror import mirror_release


class FakeHub:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def create_repo(self, repo_id, repo_type, exist_ok):
        self.calls.append(("create_repo", repo_id))
        if self.fail_at == "create_repo":
            raise RuntimeError("403 forbidden")

    def upload_folder(self, *, repo_id, folder_path, path_in_repo, repo_type):
        self.calls.append(("upload_folder", repo_id))
        if self.fail_at == "upload_folder":
            raise RuntimeError("500")


def test_mirror_happy_path(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub/b.parquet").write_bytes(b"PAR1")
    hub = FakeHub()
    res = mirror_release(hub, repo_id="denis/latent-imagination-replay",
                         repo_type="dataset", folder=tmp_path)
    assert res.files_uploaded == 2
    assert res.url.endswith("denis/latent-imagination-replay")
    assert [c[0] for c in hub.calls] == ["create_repo", "upload_folder"]


def test_missing_or_empty_folder_refused(tmp_path):
    with pytest.raises(SchemaError) as ei:
        mirror_release(FakeHub(), repo_id="x/y", repo_type="dataset", folder=tmp_path / "nope")
    assert ei.value.code == "LI-HF-001"
    with pytest.raises(SchemaError) as ei2:
        mirror_release(FakeHub(), repo_id="x/y", repo_type="dataset", folder=tmp_path)
    assert ei2.value.code == "LI-HF-002"


def test_only_dataset_mirror(tmp_path):
    (tmp_path / "f").write_text("x")
    with pytest.raises(SchemaError) as ei:
        mirror_release(FakeHub(), repo_id="x/y", repo_type="model", folder=tmp_path)
    assert ei.value.code == "LI-HF-001"


def test_hub_failure_is_coded(tmp_path):
    (tmp_path / "f").write_text("x")
    hub = FakeHub(fail_at="upload_folder")
    with pytest.raises(SchemaError) as ei:
        mirror_release(hub, repo_id="x/y", repo_type="dataset", folder=tmp_path)
    assert ei.value.code == "LI-HF-003"
