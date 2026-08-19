import hashlib
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class IntakeError(Exception):
    """Bad or unusable source input. Callers map this to HTTP 400."""


@dataclass
class Workspace:
    path: Path
    files: list[str] | None  # None means "scan the whole tree"


def repo_key_from_url(url: str) -> str:
    match = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not match:
        raise IntakeError(f"Could not parse a repository name from {url!r}")
    return f"{match.group(1).lower()}/{match.group(2).lower()}"


def repo_key_from_bytes(data: bytes) -> str:
    return f"zip:{hashlib.sha256(data).hexdigest()[:16]}"


def _clone(url: str, dest: Path) -> None:
    result = subprocess.run(
        ["git", "clone", "--quiet", url, str(dest)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise IntakeError(f"Could not clone repository: {result.stderr.strip()[:200]}")


def _extract(zip_path: str, dest: Path) -> None:
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, FileNotFoundError) as exc:
        raise IntakeError("Uploaded file is not a readable zip archive") from exc
    with archive:
        dest_root = dest.resolve()
        for member in archive.namelist():
            target = (dest / member).resolve()
            # Zip-slip guard: a member must not escape the workspace.
            if not target.is_relative_to(dest_root):
                raise IntakeError(f"Archive entry escapes the workspace: {member!r}")
        archive.extractall(dest)


def _changed_files(repo: Path, base_ref: str, head_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        cwd=repo, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise IntakeError(f"Could not diff {base_ref}...{head_ref}: {result.stderr.strip()[:200]}")
    return [line for line in result.stdout.splitlines() if (repo / line).exists()]


@contextmanager
def prepare(
    source_type: str,
    source_ref: str,
    base_ref: str | None = None,
    head_ref: str | None = None,
) -> Iterator[Workspace]:
    """Materialize the code under scan in a temp dir, always cleaned up."""
    workspace = Path(tempfile.mkdtemp(prefix="vibeguard-"))
    try:
        if source_type == "git":
            source = Path(source_ref)
            if source.is_dir():
                shutil.copytree(source, workspace, dirs_exist_ok=True)
            else:
                _clone(source_ref, workspace)
        elif source_type == "zip":
            _extract(source_ref, workspace)
        else:
            raise IntakeError(f"Unknown source type {source_type!r}")

        files = None
        if base_ref and head_ref:
            files = _changed_files(workspace, base_ref, head_ref)
        yield Workspace(path=workspace, files=files)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
