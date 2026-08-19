import json
import shutil

import pytest

from app.scanners import semgrep_scan
from app.scanners.base import ScannerUnavailable

SAMPLE_OUTPUT = json.dumps({
    "results": [
        {
            "check_id": "python.lang.security.audit.eval-detected",
            "path": "app.py",
            "start": {"line": 11},
            "extra": {"severity": "ERROR", "message": "Detected eval on user input"},
        },
        {
            "check_id": "python.flask.debug-enabled",
            "path": "app.py",
            "start": {"line": 22},
            "extra": {"severity": "WARNING", "message": "Flask debug mode enabled"},
        },
    ]
})


def test_parses_results_into_findings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        semgrep_scan, "run_tool",
        lambda cmd, cwd, timeout=600: type(
            "R", (), {"returncode": 0, "stdout": SAMPLE_OUTPUT, "stderr": ""}
        )(),
    )
    findings = semgrep_scan.scan(tmp_path)
    assert len(findings) == 2
    assert findings[0].tool == "semgrep"
    assert findings[0].severity == "high"
    assert findings[0].category == "security"
    assert findings[0].file == "app.py"
    assert findings[0].line == 11
    assert "eval" in findings[0].message
    assert findings[1].severity == "medium"


def test_unparseable_output_yields_no_findings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        semgrep_scan, "run_tool",
        lambda cmd, cwd, timeout=600: type(
            "R", (), {"returncode": 2, "stdout": "not json", "stderr": "boom"}
        )(),
    )
    assert semgrep_scan.scan(tmp_path) == []


def test_diff_mode_passes_only_changed_files(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, cwd, timeout=600):
        captured["cmd"] = cmd
        return type("R", (), {"returncode": 0, "stdout": '{"results": []}', "stderr": ""})()

    monkeypatch.setattr(semgrep_scan, "run_tool", fake_run)
    semgrep_scan.scan(tmp_path, files=["app.py"])
    assert captured["cmd"][-1] == "app.py"


@pytest.mark.skipif(shutil.which("semgrep") is None, reason="semgrep not installed")
def test_real_semgrep_finds_injection(fixture_repo):
    findings = semgrep_scan.scan(fixture_repo)
    assert any("eval" in f.message.lower() or "eval" in f.file for f in findings)
