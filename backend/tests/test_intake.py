import io
import zipfile
from pathlib import Path

import pytest

from app.intake import (IntakeError, prepare, repo_key_from_bytes,
                        repo_key_from_url)


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_repo_key_from_url_normalizes():
    assert repo_key_from_url("https://github.com/Acme/Demo.git") == "acme/demo"
    assert repo_key_from_url("https://github.com/Acme/Demo/") == "acme/demo"


def test_repo_key_from_bytes_is_stable():
    assert repo_key_from_bytes(b"hello") == repo_key_from_bytes(b"hello")
    assert repo_key_from_bytes(b"hello") != repo_key_from_bytes(b"world")
    assert repo_key_from_bytes(b"hello").startswith("zip:")


def test_zip_intake_extracts_and_cleans_up(tmp_path):
    zip_path = tmp_path / "src.zip"
    zip_path.write_bytes(_zip_bytes({"app.py": "print(1)\n"}))

    with prepare("zip", str(zip_path)) as ws:
        workspace = ws.path
        assert (workspace / "app.py").read_text() == "print(1)\n"
        assert ws.files is None
    assert not workspace.exists()


def test_zip_slip_is_rejected(tmp_path):
    zip_path = tmp_path / "evil.zip"
    zip_path.write_bytes(_zip_bytes({"../escaped.py": "pwned"}))

    with pytest.raises(IntakeError):
        with prepare("zip", str(zip_path)):
            pass
    assert not (tmp_path.parent / "escaped.py").exists()


def test_unknown_source_type_rejected():
    with pytest.raises(IntakeError):
        with prepare("carrier-pigeon", "somewhere"):
            pass


def test_diff_mode_lists_only_changed_files(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *args: subprocess.run(args, cwd=repo, check=True, capture_output=True)
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@t.com")
    run("git", "config", "user.name", "t")
    (repo / "kept.py").write_text("a = 1\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "base")
    (repo / "changed.py").write_text("b = 2\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "head")

    with prepare("git", str(repo), base_ref="HEAD~1", head_ref="HEAD") as ws:
        assert ws.files == ["changed.py"]
