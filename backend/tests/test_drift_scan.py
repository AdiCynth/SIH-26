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
