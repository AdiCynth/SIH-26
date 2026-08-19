import hashlib
import re
from collections import defaultdict
from pathlib import Path

import lizard

from app.scanners.base import RawFinding

TOOL = "lizard"
MAX_COMPLEXITY = 10
MAX_LENGTH = 60
MIN_DUPLICATE_LINES = 5
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}

# Keywords worth preserving across the languages lizard handles; everything else
# that looks like an identifier is a name and gets normalized away.
_KEYWORDS = {
    "if", "else", "elif", "for", "while", "return", "break", "continue", "def",
    "class", "try", "except", "finally", "raise", "with", "as", "import", "from",
    "in", "is", "not", "and", "or", "None", "True", "False", "function", "var",
    "let", "const", "new", "this", "self", "null", "true", "false", "public",
    "private", "static", "void", "int", "float", "str", "bool", "throw", "catch",
}
_IDENT = re.compile(r"[A-Za-z_]\w*")
_STRING = re.compile(r'"[^"]*"|\'[^\']*\'')


def _mask_strings(line: str) -> str:
    """Replace quoted spans with a placeholder derived from their own content,
    so literal text doesn't drive the fingerprint but distinct literals don't
    collide either. The placeholder is digit-only (no leading letter) so the
    later identifier substitution leaves it alone."""
    def repl(match: re.Match[str]) -> str:
        content = match.group(0)[1:-1]
        digest = str(int(hashlib.sha1(content.encode()).hexdigest(), 16))[:12]
        return f'"#{digest}#"'
    return _STRING.sub(repl, line)


def _normalize_line(line: str) -> str:
    """Normalize a line by masking string literal content, then replacing
    non-keyword identifiers with 'V'."""
    masked = _mask_strings(line.strip())
    return _IDENT.sub(lambda m: m.group(0) if m.group(0) in _KEYWORDS else "V", masked)


def _candidate_files(workspace: Path, files: list[str] | None) -> list[Path]:
    if files:
        return [workspace / name for name in files if (workspace / name).is_file()]
    return [
        path for path in workspace.rglob("*")
        if path.is_file() and not SKIP_DIRS & set(path.relative_to(workspace).parts)
    ]


def _body_fingerprint(path: Path, start: int, end: int) -> str | None:
    """Hash a function body with identifiers normalized, so near-copies collide."""
    try:
        lines = path.read_text(errors="ignore").splitlines()[start - 1 : end]
    except OSError:
        return None
    # Skip the first line (def statement) and only hash the body
    body_lines = lines[1:] if len(lines) > 1 else lines
    normalized = [_normalize_line(line) for line in body_lines if line.strip()]
    if len(normalized) < MIN_DUPLICATE_LINES:
        return None
    return hashlib.sha256("\n".join(normalized).encode()).hexdigest()


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    findings: list[RawFinding] = []
    by_fingerprint: dict[str, list[tuple[str, int, str]]] = defaultdict(list)

    for path in _candidate_files(workspace, files):
        try:
            analysis = lizard.analyze_file(str(path))
        except Exception:
            continue  # lizard has no parser for this file type; nothing to say about it.
        relative = str(path.relative_to(workspace))

        for func in analysis.function_list:
            if func.cyclomatic_complexity > MAX_COMPLEXITY:
                findings.append(RawFinding(
                    tool=TOOL, severity="medium", category="vibe-debt",
                    file=relative, line=func.start_line,
                    message=f"Function '{func.name}' has cyclomatic complexity "
                            f"{func.cyclomatic_complexity} (threshold {MAX_COMPLEXITY}). "
                            f"Hard to test and easy to break on the next edit.",
                ))
            if func.length > MAX_LENGTH:
                findings.append(RawFinding(
                    tool=TOOL, severity="low", category="vibe-debt",
                    file=relative, line=func.start_line,
                    message=f"Function '{func.name}' is {func.length} lines long "
                            f"(threshold {MAX_LENGTH}). Likely doing several jobs at once.",
                ))

            fingerprint = _body_fingerprint(path, func.start_line, func.end_line)
            if fingerprint:
                by_fingerprint[fingerprint].append((relative, func.start_line, func.name))

    for locations in by_fingerprint.values():
        if len(locations) < 2:
            continue
        names = ", ".join(f"{name} ({file}:{line})" for file, line, name in locations)
        first_file, first_line, _ = locations[0]
        findings.append(RawFinding(
            tool=TOOL, severity="low", category="vibe-debt",
            file=first_file, line=first_line,
            message=f"Duplicate logic: identical function bodies in {names}. "
                    f"Fixing a bug in one leaves the copies broken.",
        ))

    return findings
