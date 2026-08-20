import io
import zipfile
from pathlib import Path

import pytest

from app.intake import (IntakeError, _extract, prepare, repo_key_from_bytes,
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


def test_zip_slip_prefix_collision_is_rejected(tmp_path):
    # A member of the form "../<dest-basename><suffix>/..." resolves to a
    # sibling directory whose path string has dest's path string as a
    # prefix. A naive str.startswith() containment check would wrongly
    # accept this; Path.is_relative_to() must reject it.
    dest = tmp_path / "ws"
    dest.mkdir()
    zip_path = tmp_path / "evil.zip"
    zip_path.write_bytes(_zip_bytes({"../ws_sibling/evil.py": "pwned"}))

    with pytest.raises(IntakeError):
        _extract(str(zip_path), dest)
    assert not (tmp_path / "ws_sibling").exists()


def test_local_source_type_rejects_a_non_directory(tmp_path):
    with pytest.raises(IntakeError):
        with prepare("local", str(tmp_path / "nope")):
            pass


def test_git_source_type_never_reads_a_local_directory(tmp_path):
    """A directory path must not be silently treated as a repo to copy — that was
    an arbitrary-server-path read sitting on the production path."""
    repo = tmp_path / "secrets"
    repo.mkdir()
    (repo / "id_rsa").write_text("PRIVATE KEY\n")

    with pytest.raises(IntakeError):
        with prepare("git", str(repo)):
            pass


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

    with prepare("local", str(repo), base_ref="HEAD~1", head_ref="HEAD") as ws:
        assert ws.files == ["changed.py"]


def test_diff_mode_excludes_deleted_files(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *args: subprocess.run(args, cwd=repo, check=True, capture_output=True)
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@t.com")
    run("git", "config", "user.name", "t")
    (repo / "kept.py").write_text("a = 1\n")
    (repo / "removed.py").write_text("x = 1\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "base")
    (repo / "kept.py").write_text("a = 2\n")
    (repo / "removed.py").unlink()
    run("git", "add", "-A")
    run("git", "commit", "-qm", "head")

    with prepare("local", str(repo), base_ref="HEAD~1", head_ref="HEAD") as ws:
        assert ws.files == ["kept.py"]


def test_diff_mode_works_against_cloned_remote_non_default_branch(tmp_path):
    import subprocess

    origin = tmp_path / "origin"
    origin.mkdir()
    run = lambda *args: subprocess.run(args, cwd=origin, check=True, capture_output=True)
    run("git", "init", "-q", "-b", "main")
    run("git", "config", "user.email", "t@t.com")
    run("git", "config", "user.name", "t")
    (origin / "main.py").write_text("a = 1\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "base")
    run("git", "checkout", "-qb", "feature")
    (origin / "feature.py").write_text("b = 2\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "feature work")
    run("git", "checkout", "-q", "main")

    with prepare("git", f"file://{origin}", base_ref="main", head_ref="feature") as ws:
        assert ws.files == ["feature.py"]
