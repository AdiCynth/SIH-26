import ast
import os
import re
from pathlib import PurePosixPath

TOOL = "drift"
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}
PY_EXT = {".py"}
JS_EXT = {".js", ".jsx", ".mjs", ".ts", ".tsx"}

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
