# Integration Drift Simulator + False-Positive Benchmark — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn two SIH slide claims into running, demoable code — a blast-radius
analysis for diff scans, and a measured false-positive rate for the scanners.

**Architecture:** Part A adds a fifth scanner module that satisfies the existing
`scan(workspace, files)` protocol, so the pipeline change is one list entry. It
builds an import graph over the already-cloned workspace, reverses it, and does a
bounded BFS out from the diff's changed files. Part B adds a standalone benchmark
runner that drives the existing scanners over a labeled corpus and reports
precision / false-positive rate against a target.

**Tech Stack:** Python 3.11, stdlib `ast` + `re` + `collections` (no graph
library), stdlib `json` + `argparse` (no pandas), pytest.

**Spec:** No separate spec — both features were scoped in conversation on
2026-08-22 as follow-ups to the judge feedback on the SIH26_139 submission. They
were listed as out of scope in
`docs/superpowers/specs/2026-08-19-vibeguard-mvp-design.md:47-48`; this plan
brings the drift simulator in and adds the measurement the AI claim needs. The
Tribal Knowledge Graph remains out of scope.

**Part independence:** Part A (Tasks 1-4) and Part B (Tasks 5-7) share no code
and can be executed in either order, or separately.

## Global Constraints

- Python 3.11 (`backend/README.md` explains the pin). Run everything from
  `backend/` with the venv active: `source .venv/bin/activate`.
- **No new runtime dependencies.** Both features use only the stdlib plus what
  `backend/requirements.txt` already pins.
- A scanner that cannot run must raise, never return `[]` — a silent empty
  result reads as a clean scan. This is the bug fixed in commit `7e5f952`; do
  not reintroduce it.
- New finding category is exactly `"drift"` (5 chars; `Finding.category` is
  `String(16)`).
- Existing style: no docstring on trivial helpers, `# ponytail:` comments mark
  deliberate shortcuts with their ceiling.

---

## Part A — Integration Drift Simulator

### Task 1: Import extraction and module resolution

Builds the two halves of the graph's edge data: what each file imports, and
which repo file a given import specifier refers to.

**Files:**
- Create: `backend/app/scanners/drift_scan.py`
- Test: `backend/tests/test_drift_scan.py`

**Interfaces:**
- Consumes: `RawFinding` from `app.scanners.base` (Task 3 only).
- Produces:
  - `_python_imports(source: str, rel: PurePosixPath) -> list[str]` — dotted
    module names, relative imports already absolutized against `rel`.
  - `_module_keys(rel: PurePosixPath) -> list[str]` — every dotted name by which
    a Python file can be imported.
  - `_js_imports(source: str) -> list[str]` — raw specifier strings.
  - `_resolve_js(spec: str, rel: PurePosixPath, files: set[str]) -> list[str]` —
    repo-relative paths a JS specifier resolves to (empty for npm packages).
  - `PY_EXT`, `JS_EXT`, `SKIP_DIRS` module constants.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_drift_scan.py`:

```python
from pathlib import PurePosixPath

from app.scanners import drift_scan


def test_module_keys_covers_every_path_suffix():
    keys = drift_scan._module_keys(PurePosixPath("app/scanners/deps_scan.py"))
    assert "app.scanners.deps_scan" in keys
    assert "scanners.deps_scan" in keys
    assert "deps_scan" in keys


def test_module_keys_of_package_init_names_the_package():
    keys = drift_scan._module_keys(PurePosixPath("app/scanners/__init__.py"))
    assert "app.scanners" in keys
    assert "scanners" in keys
    assert "app.scanners.__init__" not in keys


def test_python_imports_plain_and_from():
    source = "import os\nfrom app.db import SessionLocal\n"
    names = drift_scan._python_imports(source, PurePosixPath("app/pipeline.py"))
    assert "os" in names
    assert "app.db" in names
    assert "app.db.SessionLocal" in names


def test_python_imports_resolves_relative_imports():
    source = "from . import base\nfrom ..config import settings\n"
    names = drift_scan._python_imports(source, PurePosixPath("app/scanners/x.py"))
    assert "app.scanners.base" in names
    assert "app.config" in names


def test_python_imports_survives_syntax_error():
    assert drift_scan._python_imports("def (:\n", PurePosixPath("a.py")) == []


def test_js_imports_finds_every_form():
    source = (
        "import a from './a';\n"
        "const b = require('../b');\n"
        "const c = await import('./c.js');\n"
        "import './styles.css';\n"
        "import x from 'react';\n"
    )
    specs = drift_scan._js_imports(source)
    assert {"./a", "../b", "./c.js", "./styles.css", "react"} <= set(specs)


def test_resolve_js_tries_extensions_and_index():
    files = {"src/a.ts", "src/lib/index.js"}
    assert drift_scan._resolve_js("./a", PurePosixPath("src/main.ts"), files) == ["src/a.ts"]
    assert drift_scan._resolve_js("./lib", PurePosixPath("src/main.ts"), files) == ["src/lib/index.js"]


def test_resolve_js_ignores_npm_packages():
    assert drift_scan._resolve_js("react", PurePosixPath("src/main.ts"), {"src/a.ts"}) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_drift_scan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.scanners.drift_scan'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/scanners/drift_scan.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_drift_scan.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/scanners/drift_scan.py backend/tests/test_drift_scan.py
git commit -m "feat: import extraction and module resolution for drift analysis"
```

---

### Task 2: Reverse dependency graph and bounded blast radius

**Files:**
- Modify: `backend/app/scanners/drift_scan.py`
- Test: `backend/tests/test_drift_scan.py`

**Interfaces:**
- Consumes: `_python_imports`, `_module_keys`, `_js_imports`, `_resolve_js`,
  `PY_EXT`, `JS_EXT`, `SKIP_DIRS` from Task 1.
- Produces:
  - `_source_files(workspace: Path) -> list[str]` — repo-relative posix paths.
  - `_dependents(workspace: Path, files: list[str]) -> dict[str, set[str]]` —
    `dependents[target] = {importers}`.
  - `_blast_radius(dependents, seeds, max_depth) -> dict[str, tuple[int, str]]` —
    `{impacted_file: (depth, originating_seed)}`, seeds excluded.
  - `MAX_DEPTH` constant.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_drift_scan.py`:

```python
def _write(tmp_path, name, body):
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body)


def test_dependents_maps_python_importer_to_target(tmp_path):
    _write(tmp_path, "a.py", "VALUE = 1\n")
    _write(tmp_path, "b.py", "import a\n")
    dependents = drift_scan._dependents(tmp_path, drift_scan._source_files(tmp_path))
    assert dependents["a.py"] == {"b.py"}


def test_dependents_maps_js_relative_import(tmp_path):
    _write(tmp_path, "src/a.ts", "export const a = 1;\n")
    _write(tmp_path, "src/b.ts", "import { a } from './a';\n")
    dependents = drift_scan._dependents(tmp_path, drift_scan._source_files(tmp_path))
    assert dependents["src/a.ts"] == {"src/b.ts"}


def test_source_files_skips_vendored_directories(tmp_path):
    _write(tmp_path, "a.py", "x = 1\n")
    _write(tmp_path, "node_modules/pkg/index.js", "module.exports = 1;\n")
    assert drift_scan._source_files(tmp_path) == ["a.py"]


def test_blast_radius_walks_transitively_and_records_depth():
    dependents = {"a.py": {"b.py"}, "b.py": {"c.py"}}
    radius = drift_scan._blast_radius(dependents, ["a.py"], max_depth=3)
    assert radius["b.py"][0] == 1
    assert radius["c.py"][0] == 2
    assert radius["b.py"][1] == "a.py"
    assert "a.py" not in radius, "a changed file is not collateral damage"


def test_blast_radius_respects_max_depth():
    dependents = {"a.py": {"b.py"}, "b.py": {"c.py"}}
    radius = drift_scan._blast_radius(dependents, ["a.py"], max_depth=1)
    assert "b.py" in radius
    assert "c.py" not in radius


def test_blast_radius_terminates_on_a_cycle():
    dependents = {"a.py": {"b.py"}, "b.py": {"a.py"}}
    radius = drift_scan._blast_radius(dependents, ["a.py"], max_depth=10)
    assert set(radius) == {"b.py"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_drift_scan.py -v`
Expected: FAIL — `AttributeError: module 'app.scanners.drift_scan' has no attribute '_dependents'`

- [ ] **Step 3: Write the implementation**

Add to the imports at the top of `backend/app/scanners/drift_scan.py`:

```python
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
```

(replacing the existing `from pathlib import PurePosixPath` line), and add the
constant next to `SKIP_DIRS`:

```python
MAX_DEPTH = 3
```

Then append:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_drift_scan.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/scanners/drift_scan.py backend/tests/test_drift_scan.py
git commit -m "feat: reverse import graph and bounded blast-radius walk"
```

---

### Task 3: The `scan()` entry point and pipeline wiring

**Files:**
- Modify: `backend/app/scanners/drift_scan.py`
- Modify: `backend/app/pipeline.py:15`
- Test: `backend/tests/test_drift_scan.py`, `backend/tests/test_scoring.py`

**Interfaces:**
- Consumes: `_source_files`, `_dependents`, `_blast_radius`, `MAX_DEPTH` from
  Task 2; `RawFinding` from `app.scanners.base`.
- Produces: `scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]`
  — the standard scanner protocol, same shape as `lizard_scan.scan`. Emits
  `category="drift"`.

Note: `drift` is deliberately absent from `_SECURITY_CATEGORIES` in
`app/scoring.py` and is not `"vibe-debt"`, so drift findings affect neither
score. That is intended — a blast radius is a "look here too" signal, not a
defect. Task 3 adds a test locking that in rather than changing `scoring.py`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_drift_scan.py`:

```python
def test_full_mode_produces_nothing(tmp_path):
    _write(tmp_path, "a.py", "VALUE = 1\n")
    _write(tmp_path, "b.py", "import a\n")
    assert drift_scan.scan(tmp_path, None) == []


def test_diff_mode_flags_the_importer_of_a_changed_file(tmp_path):
    _write(tmp_path, "a.py", "VALUE = 1\n")
    _write(tmp_path, "b.py", "import a\n")
    findings = drift_scan.scan(tmp_path, ["a.py"])
    assert [f.file for f in findings] == ["b.py"]
    assert findings[0].category == "drift"
    assert findings[0].tool == "drift"
    assert "a.py" in findings[0].message


def test_severity_falls_off_with_distance(tmp_path):
    _write(tmp_path, "a.py", "VALUE = 1\n")
    _write(tmp_path, "b.py", "import a\n")
    _write(tmp_path, "c.py", "import b\n")
    by_file = {f.file: f for f in drift_scan.scan(tmp_path, ["a.py"])}
    assert by_file["b.py"].severity == "medium"
    assert by_file["c.py"].severity == "low"


def test_changed_files_are_never_their_own_finding(tmp_path):
    _write(tmp_path, "a.py", "VALUE = 1\n")
    _write(tmp_path, "b.py", "import a\n")
    findings = drift_scan.scan(tmp_path, ["a.py", "b.py"])
    assert findings == []


def test_unknown_changed_file_is_ignored(tmp_path):
    _write(tmp_path, "a.py", "VALUE = 1\n")
    assert drift_scan.scan(tmp_path, ["README.md"]) == []
```

Append to `backend/tests/test_scoring.py`:

```python
def test_drift_findings_move_neither_score():
    from app.scanners.base import RawFinding
    from app.scoring import security_score, vibe_debt_score

    drift = [
        RawFinding(tool="drift", severity="medium", category="drift",
                   file=f"m{i}.py", line=1, message="impacted")
        for i in range(5)
    ]
    assert security_score(drift) == 100
    assert vibe_debt_score(drift) == 100
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_drift_scan.py tests/test_scoring.py -v`
Expected: FAIL — `AttributeError: module 'app.scanners.drift_scan' has no attribute 'scan'`
(`test_drift_findings_move_neither_score` should already PASS — it is a
regression lock on existing behaviour, not new work.)

- [ ] **Step 3: Write the implementation**

Add `from app.scanners.base import RawFinding` to the imports in
`backend/app/scanners/drift_scan.py`, add the constant beside `MAX_DEPTH`:

```python
_SEVERITY_BY_DEPTH = {1: "medium", 2: "low"}
```

and append:

```python
def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    """Files a diff did not touch but that depend on files it did.

    Full-tree scans have no changed set to walk out from, so they produce
    nothing — this only has something to say about a diff.
    """
    if not files:
        return []

    sources = _source_files(workspace)
    seeds = [rel for rel in files if rel in set(sources)]
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
            line=1,
            message=f"'{impacted}' imports changed code ({hops}, via '{origin}') "
                    f"but is not in this diff. Nothing here was re-reviewed — "
                    f"check the contract it relies on still holds.",
        ))
    return findings
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_drift_scan.py tests/test_scoring.py -v`
Expected: PASS (20 tests)

- [ ] **Step 5: Wire it into the pipeline**

In `backend/app/pipeline.py`, change the import line and the `SCANNERS` list:

```python
from app.scanners import deps_scan, drift_scan, gitleaks_scan, lizard_scan, semgrep_scan
```

```python
SCANNERS = [semgrep_scan, gitleaks_scan, deps_scan, lizard_scan, drift_scan]
```

- [ ] **Step 6: Run the whole backend suite**

Run: `python -m pytest -q`
Expected: PASS. Watch specifically for `tests/test_pipeline.py` — it asserts
against `SCANNERS`, and any test that counts scanners or asserts "all scanners
failed" behaviour now sees five, not four. Fix such assertions by updating the
expected count, not by special-casing `drift_scan`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/scanners/drift_scan.py backend/app/pipeline.py backend/tests/
git commit -m "feat: integration drift simulator flags untouched dependents of changed files"
```

---

### Task 4: Surface drift in the frontend

**Files:**
- Modify: `frontend/lib/api.ts:41`

The report page renders findings as a flat list and `FindingCard.tsx:16` prints
`finding.category` as free text, so the only change needed is the union type.

- [ ] **Step 1: Widen the category union**

In `frontend/lib/api.ts`, change:

```ts
  category: "security" | "vibe-debt" | "license";
```

to:

```ts
  category: "security" | "vibe-debt" | "license" | "drift";
```

- [ ] **Step 2: Verify the frontend still type-checks and builds**

Run from `frontend/`: `npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: render drift findings in the report"
```

---

## Part B — False-Positive Benchmark

**Scope decision, state it on the slide:** the benchmark measures findings with
`category in {"security", "license"}`. Vibe-debt and drift findings are
threshold judgements, not claims of a defect, and scoring them as
true/false positives would muddy the number the judges asked for.

**What is already proven and needs no new work:** the "never fabricates
findings" claim is architectural, and
`backend/tests/test_reasoning.py::test_extra_annotations_are_discarded` already
locks it — an out-of-range index from the model is dropped, so the annotation
list can never grow. Cite that test on the slide as *0 fabricated findings, by
construction*. Part B measures the different, unproven claim: the **scanners'**
false-positive rate.

### Task 5: A clean corpus fixture

A repo with zero real issues is the sharpest possible FP measurement — every
finding it produces is by definition a false positive.

**Files:**
- Create: `backend/tests/fixtures/clean_repo/inventory.py`
- Create: `backend/tests/fixtures/clean_repo/report.py`
- Create: `backend/tests/fixtures/clean_repo/requirements.txt`
- Test: `backend/tests/test_drift_scan.py` (reuses the fixture for an
  end-to-end drift check on real code)

- [ ] **Step 1: Write the fixture**

`backend/tests/fixtures/clean_repo/inventory.py`:

```python
"""Small, idiomatic module with no security issues and no vibe debt."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    sku: str
    quantity: int
    unit_price: float


def total_value(items: list[Item]) -> float:
    return sum(item.quantity * item.unit_price for item in items)


def low_stock(items: list[Item], threshold: int = 5) -> list[Item]:
    return [item for item in items if item.quantity < threshold]
```

`backend/tests/fixtures/clean_repo/report.py`:

```python
from inventory import Item, low_stock, total_value


def summary(items: list[Item]) -> dict[str, float | int]:
    return {
        "count": len(items),
        "value": total_value(items),
        "low_stock": len(low_stock(items)),
    }
```

`backend/tests/fixtures/clean_repo/requirements.txt`:

```
requests==2.32.3
```

Note: `requests==2.32.3` is current and advisory-free as of this plan. If
osv-scanner later reports a CVE against it, that is a true positive and the
fixture must be bumped to a clean version — do not label a real advisory as a
false positive.

- [ ] **Step 2: Add a fixture accessor and an end-to-end drift test**

In `backend/tests/conftest.py`, add beside the existing `fixture_repo` fixture:

```python
@pytest.fixture()
def clean_repo() -> Path:
    return Path(__file__).parent / "fixtures" / "clean_repo"
```

Append to `backend/tests/test_drift_scan.py`:

```python
def test_drift_on_real_fixture_flags_the_dependent_module(clean_repo):
    findings = drift_scan.scan(clean_repo, ["inventory.py"])
    assert [f.file for f in findings] == ["report.py"]
    assert findings[0].severity == "medium"
```

- [ ] **Step 3: Run the tests**

Run: `python -m pytest tests/test_drift_scan.py -v`
Expected: PASS (21 tests)

- [ ] **Step 4: Commit**

```bash
git add backend/tests/fixtures/clean_repo backend/tests/conftest.py backend/tests/test_drift_scan.py
git commit -m "test: add a clean corpus fixture for false-positive measurement"
```

---

### Task 6: Finding/label matching

The matching rule is the only non-trivial logic in the benchmark, so it gets its
own test cycle before the runner is built around it.

**Files:**
- Create: `backend/benchmark/__init__.py` (empty)
- Create: `backend/benchmark/match.py`
- Test: `backend/tests/test_benchmark.py`

**Interfaces:**
- Consumes: `RawFinding` from `app.scanners.base`.
- Produces:
  - `@dataclass Label(file: str, line: int, tool: str | None = None, note: str = "")`
  - `@dataclass Outcome(true_positives: int, false_positives: int, false_negatives: int, unmatched: list[RawFinding], missed: list[Label])`
    with properties `precision: float`, `recall: float`, `false_positive_rate: float`
  - `match(findings: list[RawFinding], labels: list[Label], tolerance: int) -> Outcome`
  - `SCORED_CATEGORIES: set[str]`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_benchmark.py`:

```python
from app.scanners.base import RawFinding
from benchmark.match import Label, match


def finding(file="app.py", line=10, tool="semgrep", category="security"):
    return RawFinding(tool=tool, severity="high", category=category,
                      file=file, line=line, message="issue")


def test_exact_match_is_a_true_positive():
    outcome = match([finding()], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.true_positives == 1
    assert outcome.false_positives == 0
    assert outcome.false_negatives == 0


def test_line_within_tolerance_still_matches():
    outcome = match([finding(line=12)], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.true_positives == 1


def test_line_outside_tolerance_is_a_false_positive_and_a_miss():
    outcome = match([finding(line=40)], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.false_positives == 1
    assert outcome.false_negatives == 1


def test_wrong_file_does_not_match():
    outcome = match([finding(file="other.py")], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.true_positives == 0
    assert outcome.false_positives == 1


def test_label_tool_is_honoured_when_set():
    labels = [Label(file="app.py", line=10, tool="gitleaks")]
    assert match([finding(tool="semgrep")], labels, tolerance=2).true_positives == 0
    assert match([finding(tool="gitleaks")], labels, tolerance=2).true_positives == 1


def test_one_label_absorbs_only_one_finding():
    """Two findings on the same line are one hit and one false positive, so a
    noisy scanner cannot inflate its own precision by repeating itself."""
    outcome = match([finding(), finding()], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.true_positives == 1
    assert outcome.false_positives == 1


def test_vibe_debt_and_drift_findings_are_not_scored():
    findings = [finding(category="vibe-debt"), finding(category="drift")]
    outcome = match(findings, [], tolerance=2)
    assert outcome.false_positives == 0
    assert outcome.unmatched == []


def test_clean_repo_findings_are_all_false_positives():
    outcome = match([finding(), finding(file="b.py")], [], tolerance=2)
    assert outcome.false_positives == 2
    assert outcome.precision == 0.0
    assert outcome.false_positive_rate == 1.0


def test_rates_of_an_empty_run_are_defined():
    outcome = match([], [], tolerance=2)
    assert outcome.precision == 1.0
    assert outcome.recall == 1.0
    assert outcome.false_positive_rate == 0.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_benchmark.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'benchmark'`

- [ ] **Step 3: Write the implementation**

Create `backend/benchmark/__init__.py` (empty file), then
`backend/benchmark/match.py`:

```python
from dataclasses import dataclass, field

from app.scanners.base import RawFinding

# Vibe-debt and drift findings are threshold judgements and "look here too"
# signals, not assertions that a defect exists. Scoring them as true or false
# positives would muddy the security number this benchmark exists to produce.
SCORED_CATEGORIES = {"security", "license"}


@dataclass(frozen=True)
class Label:
    file: str
    line: int
    tool: str | None = None
    note: str = ""


@dataclass
class Outcome:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    unmatched: list[RawFinding] = field(default_factory=list)
    missed: list[Label] = field(default_factory=list)

    @property
    def precision(self) -> float:
        reported = self.true_positives + self.false_positives
        return 1.0 if reported == 0 else self.true_positives / reported

    @property
    def recall(self) -> float:
        real = self.true_positives + self.false_negatives
        return 1.0 if real == 0 else self.true_positives / real

    @property
    def false_positive_rate(self) -> float:
        return 1.0 - self.precision


def _matches(f: RawFinding, label: Label, tolerance: int) -> bool:
    if label.tool and f.tool != label.tool:
        return False
    return f.file == label.file and abs(f.line - label.line) <= tolerance


def match(findings: list[RawFinding], labels: list[Label], tolerance: int) -> Outcome:
    """Score one repo's findings against its hand-labeled true positives.

    Each label absorbs at most one finding, so a scanner reporting the same
    issue five times books one hit and four false positives.
    """
    outcome = Outcome()
    remaining = list(labels)
    for f in findings:
        if f.category not in SCORED_CATEGORIES:
            continue
        hit = next((l for l in remaining if _matches(f, l, tolerance)), None)
        if hit is None:
            outcome.false_positives += 1
            outcome.unmatched.append(f)
        else:
            remaining.remove(hit)
            outcome.true_positives += 1
    outcome.false_negatives = len(remaining)
    outcome.missed = remaining
    return outcome
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_benchmark.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/benchmark backend/tests/test_benchmark.py
git commit -m "feat: finding/label matching for the false-positive benchmark"
```

---

### Task 7: The benchmark runner and the labeled corpus

**Files:**
- Create: `backend/benchmark/labels.json`
- Create: `backend/benchmark/run.py`
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: `Label`, `Outcome`, `match`, `SCORED_CATEGORIES` from Task 6; the
  scanner modules from `app.scanners`; `ScannerUnavailable` from
  `app.scanners.base`.
- Produces: a CLI — `python -m benchmark.run [--json OUT] [--dump]`.

- [ ] **Step 1: Write the runner**

Create `backend/benchmark/run.py`:

```python
"""Measure the scanners' false-positive rate against a hand-labeled corpus.

    python -m benchmark.run           # score the corpus, exit 1 if off target
    python -m benchmark.run --dump    # print raw findings, for labeling
"""

import argparse
import json
import sys
from pathlib import Path

from app.scanners import deps_scan, gitleaks_scan, semgrep_scan
from app.scanners.base import ScannerUnavailable
from benchmark.match import SCORED_CATEGORIES, Label, match

# Only the scanners that make security claims. Lizard and drift emit categories
# this benchmark does not score, so running them would just cost time.
SCANNERS = [semgrep_scan, gitleaks_scan, deps_scan]

ROOT = Path(__file__).resolve().parent.parent
LABELS = Path(__file__).parent / "labels.json"


def _scan(repo: Path):
    findings = []
    for scanner in SCANNERS:
        # A scanner that cannot run must abort the benchmark. Skipping it would
        # silently drop both its true and false positives and report a
        # precision figure for a tool set that never ran.
        try:
            findings.extend(scanner.scan(repo, None))
        except ScannerUnavailable as exc:
            sys.exit(f"ABORT: {scanner.__name__} unavailable ({exc}). "
                     f"Install it — a partial run reports a meaningless rate.")
    return findings


def _dump(config) -> None:
    for entry in config["corpus"]:
        repo = ROOT / entry["repo"]
        print(f"\n=== {entry['repo']} ===")
        for f in sorted(_scan(repo), key=lambda f: (f.file, f.line)):
            if f.category in SCORED_CATEGORIES:
                print(f'  {{"file": "{f.file}", "line": {f.line}, '
                      f'"tool": "{f.tool}", "note": "{f.message[:60]}"}},')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write full results here")
    parser.add_argument("--dump", action="store_true",
                        help="print raw findings as label stubs, then exit")
    args = parser.parse_args()

    config = json.loads(LABELS.read_text())
    if args.dump:
        _dump(config)
        return 0

    tolerance = config["line_tolerance"]
    target = config["target_false_positive_rate"]
    totals = {"tp": 0, "fp": 0, "fn": 0}
    rows, detail = [], []

    for entry in config["corpus"]:
        repo = ROOT / entry["repo"]
        if not repo.is_dir():
            sys.exit(f"ABORT: corpus entry {entry['repo']} does not exist")
        labels = [Label(**item) for item in entry["expected"]]
        outcome = match(_scan(repo), labels, tolerance)
        totals["tp"] += outcome.true_positives
        totals["fp"] += outcome.false_positives
        totals["fn"] += outcome.false_negatives
        rows.append((entry["repo"], outcome))
        detail.append({
            "repo": entry["repo"],
            "true_positives": outcome.true_positives,
            "false_positives": outcome.false_positives,
            "false_negatives": outcome.false_negatives,
            "precision": round(outcome.precision, 4),
            "recall": round(outcome.recall, 4),
            "spurious": [f"{f.tool} {f.file}:{f.line} {f.message[:70]}"
                         for f in outcome.unmatched],
            "missed": [f"{l.file}:{l.line} {l.note}" for l in outcome.missed],
        })

    reported = totals["tp"] + totals["fp"]
    fp_rate = 0.0 if reported == 0 else totals["fp"] / reported
    real = totals["tp"] + totals["fn"]
    recall = 1.0 if real == 0 else totals["tp"] / real

    print(f"\n{'repo':<40} {'TP':>4} {'FP':>4} {'FN':>4} {'prec':>7}")
    print("-" * 62)
    for name, outcome in rows:
        print(f"{name:<40} {outcome.true_positives:>4} "
              f"{outcome.false_positives:>4} {outcome.false_negatives:>4} "
              f"{outcome.precision:>7.1%}")
    print("-" * 62)
    print(f"{'TOTAL':<40} {totals['tp']:>4} {totals['fp']:>4} "
          f"{totals['fn']:>4} {1 - fp_rate:>7.1%}")
    print(f"\nfalse-positive rate: {fp_rate:.1%}  (target <= {target:.0%})")
    print(f"recall:              {recall:.1%}")

    for item in detail:
        for line in item["spurious"]:
            print(f"  FP  {item['repo']}: {line}")
        for line in item["missed"]:
            print(f"  FN  {item['repo']}: {line}")

    if args.json:
        args.json.write_text(json.dumps({
            "false_positive_rate": round(fp_rate, 4),
            "precision": round(1 - fp_rate, 4),
            "recall": round(recall, 4),
            "target_false_positive_rate": target,
            "totals": totals,
            "per_repo": detail,
        }, indent=2))

    if fp_rate > target:
        print(f"\nFAIL: {fp_rate:.1%} false positives exceeds the "
              f"{target:.0%} target")
        return 1
    print(f"\nPASS: within the {target:.0%} false-positive target")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write the corpus with provisional labels**

Create `backend/benchmark/labels.json`. The `vulnerable_repo` labels below are
the issues that fixture was built to contain (`app.py` line 10 `eval` on request
input, line 16 `shell=True` command injection, line 20 a debug-mode bind to
`0.0.0.0`; `config.py` lines 4-5 the synthetic AWS key pair;
`requirements.txt` line 1 `flask==0.12.2`, which carries real advisories).
Step 3 reconciles exact lines and tool names against a real run — scanners
differ on which line of a multi-line construct they anchor to.

```json
{
  "target_false_positive_rate": 0.15,
  "line_tolerance": 2,
  "corpus": [
    {
      "repo": "tests/fixtures/vulnerable_repo",
      "expected": [
        {"file": "app.py", "line": 10, "note": "eval on request input"},
        {"file": "app.py", "line": 16, "note": "shell=True command injection"},
        {"file": "app.py", "line": 20, "note": "debug server bound to 0.0.0.0"},
        {"file": "config.py", "line": 4, "tool": "gitleaks", "note": "AWS access key id"},
        {"file": "config.py", "line": 5, "tool": "gitleaks", "note": "AWS secret key"},
        {"file": "requirements.txt", "line": 1, "tool": "osv-scanner", "note": "flask 0.12.2 advisories"}
      ]
    },
    {
      "repo": "tests/fixtures/clean_repo",
      "expected": []
    }
  ]
}
```

- [ ] **Step 3: Reconcile the labels against a real run**

Run from `backend/`:

```bash
python -m benchmark.run --dump
```

Compare the dump to the labels above. For each printed finding, decide honestly:

- It names a real issue the fixture was built to contain → make sure a label
  covers it (fix the line number or `tool` if the dump disagrees).
- It is a duplicate of an issue already labeled at a different line → **leave it
  unlabeled**. It is a false positive; that is the number being measured.
- It is spurious → **leave it unlabeled**.
- `deps_scan` may report one finding per advisory for `flask==0.12.2`. Add one
  label per distinct advisory it legitimately reports; each is a real
  vulnerability, not a duplicate.

Do not add a label just to make a finding go away. Inflating the label set to
hit the target is the one failure mode that makes the whole number worthless.

- [ ] **Step 4: Run the benchmark and record the real number**

Run from `backend/`:

```bash
python -m benchmark.run --json benchmark/results.json
```

Expected: a table, an overall false-positive rate, and PASS or FAIL. **Record
the actual number — do not tune the corpus until it passes.** If the rate
exceeds 15%, that is the finding: report it, and put the observed rate on the
slide with the corpus size next to it. A measured 22% with a named method beats
a claimed 5%.

- [ ] **Step 5: Document it**

Append to `backend/README.md`:

```markdown
## Measuring the false-positive rate

The AI reasoning layer cannot invent findings — it annotates the exact index
list it is given, and out-of-range indexes are dropped
(`tests/test_reasoning.py::test_extra_annotations_are_discarded`). That is a
property of the architecture, not a rate.

The *scanners* do produce false positives, and that rate is measured:

```bash
python -m benchmark.run --json benchmark/results.json
```

The runner scans each repo in `benchmark/labels.json`, matches findings against
hand-labeled true positives (same file, line within 2, tool if the label names
one), and reports precision, recall, and the false-positive rate. One label
absorbs one finding, so a scanner that repeats itself books the repeats as
false positives. Only `security` and `license` findings are scored — vibe-debt
and drift are threshold and impact signals, not defect claims.

It exits non-zero above the target rate in `labels.json`, so it works in CI.
A scanner that is not installed aborts the run rather than being skipped: a
partial run would silently drop that tool's false positives and report a
flattering number for a tool set that never ran.
```

- [ ] **Step 6: Commit**

```bash
git add backend/benchmark backend/README.md
git commit -m "feat: false-positive benchmark over a labeled corpus"
```

---

## Self-Review

**Coverage against what was scoped:**

| Scoped item | Task |
|---|---|
| Import graph over the cloned workspace | Tasks 1-2 |
| Blast radius from diff-mode changed files | Tasks 2-3 |
| Wired into the existing pipeline, visible in the report | Tasks 3-4 |
| Labeled corpus incl. a clean repo | Tasks 5, 7 |
| Precision / FP-rate measurement with a target | Tasks 6-7 |
| "Never fabricates" evidence | Already covered by
  `test_extra_annotations_are_discarded`; cited in Task 7 Step 5, no new code |

**Type consistency check:** `_module_keys`, `_python_imports`, `_resolve_js`
take `PurePosixPath` in Tasks 1-3 and are called with `PurePosixPath` in
`_dependents`. `_blast_radius` returns `dict[str, tuple[int, str]]` in Task 2
and is unpacked as `(depth, origin)` in Task 3. `Label` fields
(`file`, `line`, `tool`, `note`) match the JSON keys in `labels.json` exactly,
since the runner constructs them with `Label(**item)`. `scan(workspace, files)`
matches the protocol `pipeline._run_scanners` calls.

**Known gap this plan does not close:** the security score still floors at 0
(`app/scoring.py:14`), so a mildly bad repo and a catastrophic one can both
read 0. Out of scope here — worth a separate one-task fix before demo day.
