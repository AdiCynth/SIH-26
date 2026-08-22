import ast
import os
import re
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath

from app.scanners.base import RawFinding

TOOL = "drift"
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}
PY_EXT = {".py"}
JS_EXT = {".js", ".jsx", ".mjs", ".ts", ".tsx"}
MAX_DEPTH = 3
_SEVERITY_BY_DEPTH = {1: "medium", 2: "low"}

_JS_IMPORT = re.compile(
    r"""(?:from|require\(|import\()\s*['"]([^'"]+)['"]"""
    r"""|import\s+['"]([^'"]+)['"]"""
)


def _module_keys(rel: PurePosixPath) -> list[str]:
    """Every dotted name by which a Python file can be imported. sys.path may
    point at any ancestor directory, so each suffix of the path is plausible."""
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].rsplit(".", 1)[0]
    return [".".join(parts[i:]) for i in range(len(parts)) if parts[i:]]


def _python_imports(source: str, rel: PurePosixPath) -> list[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    package = rel.parent.parts
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # level 1 == this package, level 2 == its parent, and so on.
                keep = len(package) - (node.level - 1)
                base = ".".join(package[:keep]) if keep > 0 else ""
            else:
                base = ""
            module = ".".join(p for p in (base, node.module or "") if p)
            if not module:
                continue
            names.append(module)
            # `from x import y` may name a submodule y, not just an attribute.
            names.extend(f"{module}.{alias.name}" for alias in node.names)
    return names


def _js_imports(source: str) -> list[str]:
    return [a or b for a, b in _JS_IMPORT.findall(source)]


def _resolve_js(spec: str, rel: PurePosixPath, files: set[str]) -> list[str]:
    if not spec.startswith("."):
        return []  # bare specifier: an npm package, not a file in this repo
    target = os.path.normpath((rel.parent / spec).as_posix()).replace(os.sep, "/")
    candidates = [target]
    candidates += [f"{target}{ext}" for ext in sorted(JS_EXT)]
    candidates += [f"{target}/index{ext}" for ext in sorted(JS_EXT)]
    return [c for c in candidates if c in files]


def _source_files(workspace: Path) -> list[str]:
    known = PY_EXT | JS_EXT
    found = []
    for path in workspace.rglob("*"):
        rel = path.relative_to(workspace)
        if not path.is_file() or path.suffix not in known:
            continue
        if SKIP_DIRS & set(rel.parts):
            continue
        found.append(rel.as_posix())
    return sorted(found)


def _dependents(workspace: Path, files: list[str]) -> dict[str, set[str]]:
    """Reverse import graph: dependents[target] = {files that import target}."""
    file_set = set(files)
    # ponytail: a module key that two files both claim maps to both, so an
    # ambiguous import adds edges to each. Over-connecting slightly widens the
    # blast radius, which is the safe direction for a "check this too" signal.
    # Resolve properly (respect sys.path / package roots) if the noise shows.
    by_key: dict[str, set[str]] = defaultdict(set)
    for rel in files:
        if PurePosixPath(rel).suffix in PY_EXT:
            for key in _module_keys(PurePosixPath(rel)):
                by_key[key].add(rel)

    dependents: dict[str, set[str]] = defaultdict(set)
    for rel in files:
        path = workspace / rel
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        posix = PurePosixPath(rel)
        targets: set[str] = set()
        if posix.suffix in PY_EXT:
            for name in _python_imports(source, posix):
                targets |= by_key.get(name, set())
        else:
            for spec in _js_imports(source):
                targets.update(_resolve_js(spec, posix, file_set))
        for target in targets - {rel}:
            dependents[target].add(rel)
    return dict(dependents)


def _blast_radius(
    dependents: dict[str, set[str]], seeds: list[str], max_depth: int
) -> dict[str, tuple[int, str]]:
    """Files reachable from the changed set, with hop count and originating seed."""
    seen: dict[str, tuple[int, str]] = {seed: (0, seed) for seed in seeds}
    queue = deque(seeds)
    while queue:
        node = queue.popleft()
        depth, origin = seen[node]
        if depth >= max_depth:
            continue
        for importer in dependents.get(node, ()):
            if importer not in seen:
                seen[importer] = (depth + 1, origin)
                queue.append(importer)
    return {f: v for f, v in seen.items() if v[0] > 0}


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    """Files a diff did not touch but that depend on files it did.

    Full-tree scans have no changed set to walk out from, so they produce
    nothing — this only has something to say about a diff.
    """
    if not files:
        return []

    sources = _source_files(workspace)
    source_set = set(sources)
    seeds = [rel for rel in files if rel in source_set]
    if not seeds:
        return []

    dependents = _dependents(workspace, sources)
    radius = _blast_radius(dependents, seeds, MAX_DEPTH)

    findings = []
    for impacted, (depth, origin) in sorted(radius.items()):
        hops = "directly" if depth == 1 else f"{depth} hops away"
        findings.append(RawFinding(
            tool=TOOL,
            severity=_SEVERITY_BY_DEPTH.get(depth, "info"),
            category="drift",
            file=impacted,
            line=0,
            message=f"'{impacted}' imports changed code ({hops}, via '{origin}') "
                    f"but is not in this diff. Nothing here was re-reviewed — "
                    f"check the contract it relies on still holds.",
        ))
    return findings
