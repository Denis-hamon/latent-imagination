"""Story 13.2 — normalisateur AST de diffs : déterminisme, abstraction,
alignement du renommage entre lignes - et +, fallback non-crash."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "ast_norm_diff", Path(__file__).resolve().parent / "ast_norm_diff.py")
an = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(an)

DIFF = """diff --git a/src/flake8/exceptions.py b/src/flake8/exceptions.py
--- a/src/flake8/exceptions.py
+++ b/src/flake8/exceptions.py
@@ -65,7 +65,7 @@ class PluginExecutionFailed(Flake8Exception):
-        self.filename = plugin_name
-        self.plugin_name = filename
+        self.filename = filename
+        self.plugin_name = plugin_name
         super().__init__(plugin_name, filename, exception)
"""


def test_deterministic():
    assert an.normalize_diff(DIFF) == an.normalize_diff(DIFF)


def test_project_identifiers_abstracted_keywords_kept():
    norm = an.normalize_diff(DIFF)
    assert "flake8" not in norm and "PluginExecutionFailed" not in norm
    assert "exceptions.py" not in norm  # chemins abstraits en PATH
    assert "self" in norm  # structure Python conservée
    assert "filename" not in norm  # nom propre abstrait en v_k


def test_rename_alignment_minus_plus():
    # le même nom sur une ligne - et une ligne + reçoit le MÊME v_k :
    # l'alignement du patch survit à l'abstraction. Ici plugin_name (v2) et
    # filename (v1) sont échangés entre - et + : les ENSEMBLES de tokens des
    # deux côtés sont identiques (mêmes noms, même table).
    norm = an.normalize_diff(DIFF)
    toks = lambda ls: {t for l in ls for t in l.split() if t.startswith("v")}
    removed = [l for l in norm.splitlines() if l.startswith("-")]
    added = [l for l in norm.splitlines() if l.startswith("+")]
    assert toks(removed) == toks(added)
    assert len(toks(removed)) == 2  # filename→v0, plugin_name→v1 (self conservé)
    assert "self" in removed[1] and "self" in added[1]


def test_header_lines_preserved_but_abstracted():
    norm = an.normalize_diff(DIFF)
    assert "diff --git a/PATH b/PATH" in norm
    assert "@@ -65,7 +65,7 @@" in norm  # contexte de classe supprimé, numéros gardés


def test_unparseable_line_fallback_no_crash():
    broken = "--- a/x\n+++ b/x\n+    def broken(:\n+go func() { return nil }\n"
    norm = an.normalize_diff(broken)
    assert isinstance(norm, str) and "v0" in norm  # identifiants abstraits quand même
    assert "func" in norm  # mot-clé Go conservé par le fallback


def test_string_literals_and_comments_removed():
    d = "+x = 'repo_specific_error_msg'  # comment about flake8 internals\n"
    norm = an.normalize_diff(d)
    assert "repo_specific_error_msg" not in norm and "comment" not in norm
    assert '"S"' in norm
