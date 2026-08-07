"""HF Hub mirror adapter (edge; the only place hub network lives).

Uses the pinned `huggingface_hub` client. The hub object is INJECTED so tests
run with a fake client — no network anywhere in the suite. Token comes from the
environment; never stored, never logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core_schema.errors import SchemaError


@dataclass(frozen=True)
class MirrorResult:
    repo_id: str
    url: str
    files_uploaded: int


class _RealHub:
    def __init__(self, token: str | None):
        from huggingface_hub import HfApi

        self._api = HfApi(token=token)

    def create_repo(self, repo_id: str, repo_type: str, exist_ok: bool) -> None:
        self._api.create_repo(repo_id=repo_id, repo_type=repo_type, exist_ok=exist_ok)

    def upload_folder(self, *, repo_id: str, folder_path: str, path_in_repo: str,
                      repo_type: str) -> object:
        return self._api.upload_folder(repo_id=repo_id, folder_path=folder_path,
                                       path_in_repo=path_in_repo, repo_type=repo_type)


def mirror_release(
    hub,
    *,
    repo_id: str,
    repo_type: str,
    folder: Path,
    path_in_repo: str = "",
) -> MirrorResult:
    """create-if-needed + upload a DEPLOYABLE artifact folder. Coded failures."""
    folder = Path(folder)
    if not folder.is_dir():
        raise SchemaError("LI-HF-001", "mirror folder missing", {"folder": str(folder)})
    if repo_type != "dataset":
        raise SchemaError("LI-HF-001", "only dataset mirrors are sanctioned", {"got": repo_type})
    files = [p for p in sorted(folder.rglob("*")) if p.is_file()]
    if not files:
        raise SchemaError("LI-HF-002", "mirror folder empty — nothing shipped", {})
    try:
        hub.create_repo(repo_id=repo_id, repo_type=repo_type, exist_ok=True)
        hub.upload_folder(repo_id=repo_id, folder_path=str(folder),
                          path_in_repo=path_in_repo, repo_type=repo_type)
    except Exception as exc:
        raise SchemaError("LI-HF-003", "hub operation failed",
                          {"err": type(exc).__name__}) from exc
    return MirrorResult(repo_id=repo_id,
                        url=f"https://huggingface.co/datasets/{repo_id}",
                        files_uploaded=len(files))


def default_hub(token: str | None) -> _RealHub:
    return _RealHub(token)
