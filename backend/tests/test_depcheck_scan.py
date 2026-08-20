import json

import pytest

from app.scanners import depcheck_scan
from app.scanners.base import ScannerUnavailable, _resolve_executable

SAMPLE_REPORT = {
    "dependencies": [
        {
            "fileName": "flask:0.12.2",
            "filePath": "/ws/requirements.txt",
            "license": "BSD-3-Clause",
            "vulnerabilities": [
                {"name": "CVE-2018-1000656", "severity": "HIGH",
                 "description": "Flask denial of service"},
                {"name": "CVE-2019-1010083", "severity": "MEDIUM",
                 "description": "Unexpected memory consumption"},
            ],
        },
        {
            "fileName": "somelib:1.0",
            "filePath": "/ws/requirements.txt",
            "license": "AGPL-3.0",
            "vulnerabilities": [],
        },
        {
            "fileName": "friendly:2.0",
            "filePath": "/ws/requirements.txt",
            "license": "LGPL-2.1",
            "vulnerabilities": [],
        },
    ]
}


@pytest.mark.parametrize(
    "text,expected",
    [("AGPL-3.0", "AGPL"), ("GPL-3.0-only", "GPL"), ("LGPL-2.1", None),
     ("MIT", None), ("", None)],
)
def test_is_copyleft(text, expected):
    assert depcheck_scan.is_copyleft(text) == expected


def _patch_report(monkeypatch, report):
    def fake_run(cmd, cwd, timeout=600):
        out_dir = cmd[cmd.index("--out") + 1]
        with open(f"{out_dir}/dependency-check-report.json", "w") as handle:
            json.dump(report, handle)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(depcheck_scan, "run_tool", fake_run)


def test_vulnerabilities_become_security_findings(tmp_path, monkeypatch):
    _patch_report(monkeypatch, SAMPLE_REPORT)
    findings = depcheck_scan.scan(tmp_path)
    vulns = [f for f in findings if f.category == "security"]
    assert len(vulns) == 2
    assert vulns[0].tool == "dependency-check"
    assert vulns[0].severity == "high"
    assert "CVE-2018-1000656" in vulns[0].message
    assert "flask:0.12.2" in vulns[0].message


def test_copyleft_licenses_become_license_findings(tmp_path, monkeypatch):
    _patch_report(monkeypatch, SAMPLE_REPORT)
    findings = depcheck_scan.scan(tmp_path)
    licenses = [f for f in findings if f.category == "license"]
    assert len(licenses) == 1
    assert licenses[0].license_id == "AGPL"
    assert licenses[0].severity == "medium"
    assert "somelib:1.0" in licenses[0].message


def test_missing_report_raises_rather_than_reporting_clean(tmp_path, monkeypatch):
    """dependency-check ran and aborted (e.g. empty NVD cache): not a clean scan."""
    monkeypatch.setattr(
        depcheck_scan, "run_tool",
        lambda cmd, cwd, timeout=600: type(
            "R", (), {"returncode": 1, "stdout": "", "stderr": "no java"}
        )(),
    )
    with pytest.raises(ScannerUnavailable, match="no java"):
        depcheck_scan.scan(tmp_path)


def test_unparseable_report_raises(tmp_path, monkeypatch):
    def fake_run(cmd, cwd, timeout=600):
        out_dir = cmd[cmd.index("--out") + 1]
        with open(f"{out_dir}/dependency-check-report.json", "w") as handle:
            handle.write("{truncated")
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "aborted"})()

    monkeypatch.setattr(depcheck_scan, "run_tool", fake_run)
    with pytest.raises(ScannerUnavailable):
        depcheck_scan.scan(tmp_path)


def test_empty_report_is_a_clean_run(tmp_path, monkeypatch):
    _patch_report(monkeypatch, {"dependencies": []})
    assert depcheck_scan.scan(tmp_path) == []


@pytest.mark.skipif(
    _resolve_executable("dependency-check.sh") == "dependency-check.sh",
    reason="dependency-check not installed"
)
def test_real_depcheck_flags_vulnerable_flask(fixture_repo):
    findings = depcheck_scan.scan(fixture_repo)
    assert any("flask" in f.message.lower() for f in findings)
