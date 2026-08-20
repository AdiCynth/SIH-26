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


# A 43KB zip bomb expands to gigabytes. Refuse before writing anything to disk.
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024


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
        declared = sum(info.file_size for info in archive.infolist())
        if declared > MAX_UNCOMPRESSED_BYTES:
            raise IntakeError(
                f"Archive expands to {declared // (1024 * 1024)}MB, over the "
                f"{MAX_UNCOMPRESSED_BYTES // (1024 * 1024)}MB limit"
            )
        dest_root = dest.resolve()
        for member in archive.namelist():
            target = (dest / member).resolve()
            # Zip-slip guard: a member must not escape the workspace.
            if not target.is_relative_to(dest_root):
                raise IntakeError(f"Archive entry escapes the workspace: {member!r}")
        archive.extractall(dest)


def _resolve_ref(repo: Path, ref: str) -> str:
    """Resolve a ref that may only exist as a remote-tracking branch after a clone."""
    for candidate in (ref, f"origin/{ref}"):
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            cwd=repo, capture_output=True, text=True, timeout=30,
        )
        if probe.returncode == 0:
            return candidate
    raise IntakeError(f"Unknown ref {ref!r}")


def _changed_files(repo: Path, base_ref: str, head_ref: str) -> list[str]:
    base = _resolve_ref(repo, base_ref)
    head = _resolve_ref(repo, head_ref)
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=d", f"{base}...{head}"],
        cwd=repo, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise IntakeError(f"Could not diff {base_ref}...{head_ref}: {result.stderr.strip()[:200]}")
    return result.stdout.splitlines()


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
            _clone(source_ref, workspace)
        elif source_type == "local":
            # Copying a server-local directory is a test affordance. It is reachable
            # only when the caller says so explicitly — never by sniffing whether a
            # source_ref happens to name a directory, which put an arbitrary-path
            # read on the production path.
            source = Path(source_ref)
            if not source.is_dir():
                raise IntakeError(f"Not a directory: {source_ref!r}")
            shutil.copytree(source, workspace, dirs_exist_ok=True)
        elif source_type == "zip":
            _extract(source_ref, workspace)
        else:
            raise IntakeError(f"Unknown source type {source_type!r}")

        files = None
        if base_ref and head_ref:
            head = _resolve_ref(workspace, head_ref)
            checkout = subprocess.run(
                ["git", "checkout", "--quiet", "--detach", head],
                cwd=workspace, capture_output=True, text=True, timeout=60,
            )
            if checkout.returncode != 0:
                raise IntakeError(f"Could not check out {head_ref!r}: {checkout.stderr.strip()[:200]}")
            files = _changed_files(workspace, base_ref, head_ref)
        yield Workspace(path=workspace, files=files)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
