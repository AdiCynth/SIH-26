import json

import pytest

from app.scanners import gitleaks_scan
from app.scanners.base import _resolve_executable

SAMPLE_REPORT = [
    {
        "RuleID": "aws-access-token",
        "Description": "AWS Access Key",
        "File": "config.py",
        "StartLine": 1,
        "Secret": "AKIAIOSFODNN7EXAMPLE",
    }
]


def test_parses_report_into_high_severity_findings(tmp_path, monkeypatch):
    def fake_run(cmd, cwd, timeout=600):
        report_path = cmd[cmd.index("--report-path") + 1]
        with open(report_path, "w") as handle:
            json.dump(SAMPLE_REPORT, handle)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(gitleaks_scan, "run_tool", fake_run)
    findings = gitleaks_scan.scan(tmp_path)
    assert len(findings) == 1
    assert findings[0].tool == "gitleaks"
    assert findings[0].severity == "high"
    assert findings[0].category == "security"
    assert findings[0].file == "config.py"
    assert findings[0].line == 1
    assert "AWS Access Key" in findings[0].message
    assert "AKIAIOSFODNN7EXAMPLE" not in findings[0].message  # never echo the secret


def test_missing_report_yields_no_findings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gitleaks_scan, "run_tool",
        lambda cmd, cwd, timeout=600: type(
            "R", (), {"returncode": 1, "stdout": "", "stderr": "boom"}
        )(),
    )
    assert gitleaks_scan.scan(tmp_path) == []


def test_diff_mode_filters_to_changed_files(tmp_path, monkeypatch):
    def fake_run(cmd, cwd, timeout=600):
        report_path = cmd[cmd.index("--report-path") + 1]
        with open(report_path, "w") as handle:
            json.dump(
                SAMPLE_REPORT + [{"RuleID": "x", "Description": "Other",
                                  "File": "untouched.py", "StartLine": 2}],
                handle,
            )
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(gitleaks_scan, "run_tool", fake_run)
    findings = gitleaks_scan.scan(tmp_path, files=["config.py"])
    assert [f.file for f in findings] == ["config.py"]


@pytest.mark.skipif(_resolve_executable("gitleaks") == "gitleaks", reason="gitleaks not installed")
def test_real_gitleaks_finds_planted_secret(fixture_repo):
    findings = gitleaks_scan.scan(fixture_repo)
    assert any(f.file.endswith("config.py") for f in findings)
