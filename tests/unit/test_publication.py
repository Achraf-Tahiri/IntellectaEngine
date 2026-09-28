import hashlib
import shutil
import subprocess

import pytest


def test_gitignore_excludes_private_runtime_files_but_keeps_examples(project_root, tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    shutil.copyfile(project_root / ".gitignore", tmp_path / ".gitignore")
    excluded = [
        ".env",
        ".env.staging",
        ".streamlit/secrets.toml",
        "src/intellectaengine/core/__pycache__/module.pyc",
        "assets/Chinook.db",
        "src/intellectaengine/assets/private.db",
        "src/intellectaengine/assets/Chinook.db-wal",
        "data/chroma/index.bin",
        "uploads/private.pdf",
        "models/weights.safetensors",
        "private.sqlite3",
        "private.db-wal",
        ".pytest_cache/results",
        "exports/private-chat.json",
    ]
    included = [
        ".env.example",
        ".python-version",
        "src/intellectaengine/assets/Chinook.db",
        "examples/documents/sample.pdf",
        "docs/screenshots/demo.png",
        "uv.lock",
    ]
    result = subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "--stdin"],
        input="\n".join(excluded + included) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert set(result.stdout.splitlines()) == set(excluded)


def test_bundled_sample_matches_reviewed_file(project_root):
    # The sole database allowed through .gitignore must remain the reviewed,
    # public sample. Update the notice and this digest after any replacement.
    digest = hashlib.sha256(
        (project_root / "src/intellectaengine/assets/Chinook.db").read_bytes()
    ).hexdigest()
    assert digest == "84f5d9143ac4deebdb81650ab650e226d909e660106846b119a5c47c33f94c13"


def test_no_ignored_files_are_tracked(project_root):
    tracked = subprocess.run(
        ["git", "-C", str(project_root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if tracked.returncode:
        pytest.skip("Git metadata is unavailable; index and history require a real checkout")
    ignored = subprocess.run(
        ["git", "-C", str(project_root), "check-ignore", "--no-index", "-z", "--stdin"],
        input=tracked.stdout,
        capture_output=True,
        check=False,
    )
    assert ignored.returncode in (0, 1), "Git ignore check failed"
    assert not ignored.stdout, "Ignored/private artifacts are tracked; inspect git ls-files"
