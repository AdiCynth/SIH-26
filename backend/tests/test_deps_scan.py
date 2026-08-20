import json

import pytest

from app.scanners import deps_scan
from app.scanners.base import ScannerUnavailable, _resolve_executable

SAMPLE_OUTPUT = json.dumps({
    "results": [
        {
            "source": {"path": "/ws/requirements.txt", "type": "lockfile"},
            "packages": [
                {
                    "package": {"name": "flask", "version": "0.12.2", "ecosystem": "PyPI"},
                    "licenses": ["BSD-3-Clause"],
                    "groups": [
                        {"ids": ["PYSEC-2018-66"], "aliases": ["CVE-2018-1000656", "PYSEC-2018-66"],
                         "max_severity": "8.7"},
                        {"ids": ["PYSEC-2019-179"], "aliases": ["CVE-2019-1010083", "PYSEC-2019-179"],
                         "max_severity": "5.5"},
                    ],
                },
                {
                    "package": {"name": "somelib", "version": "1.0", "ecosystem": "PyPI"},
                    "licenses": ["AGPL-3.0"],
                    "groups": [],
                },
                {
                    "package": {"name": "friendly", "version": "2.0", "ecosystem": "PyPI"},
                    "licenses": ["LGPL-2.1"],
                    "groups": [],
                },
                {
                    "package": {"name": "unclear", "version": "1.0", "ecosystem": "PyPI"},
                    "licenses": ["non-standard"],
                    "groups": [],
                },
            ],
        }
    ]
})


@pytest.mark.parametrize(
    "text,expected",
    [("AGPL-3.0", "AGPL"), ("GPL-3.0-only", "GPL"), ("LGPL-2.1", None),
     ("MIT", None), ("", None)],
)
def test_is_copyleft(text, expected):
    assert deps_scan.is_copyleft(text) == expected


@pytest.mark.parametrize(
    "score,expected",
    [
        ("9.0", "critical"), ("10.0", "critical"),
        ("8.9", "high"), ("7.0", "high"),
        ("6.9", "medium"), ("4.0", "medium"),
        ("3.9", "low"), ("0.1", "low"),
        ("0", "medium"), ("0.0", "medium"),
        (None, "medium"), ("", "medium"), ("not-a-number", "medium"),
    ],
)
def test_severity_from_score_boundaries(score, expected):
    assert deps_scan._severity_from_score(score) == expected


def _patch_output(monkeypatch, stdout, returncode=1, stderr=""):
    monkeypatch.setattr(
        deps_scan, "run_tool",
        lambda cmd, cwd, timeout=600: type(
            "R", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr}
        )(),
    )


def test_vulnerabilities_become_security_findings(tmp_path, monkeypatch):
    _patch_output(monkeypatch, SAMPLE_OUTPUT)
    findings = deps_scan.scan(tmp_path)
    vulns = [f for f in findings if f.category == "security"]
    assert len(vulns) == 2
    assert vulns[0].tool == "osv-scanner"
    assert vulns[0].severity == "high"
    assert "CVE-2018-1000656" in vulns[0].message
    assert "flask" in vulns[0].message
    assert vulns[1].severity == "medium"


def test_copyleft_licenses_become_license_findings(tmp_path, monkeypatch):
    _patch_output(monkeypatch, SAMPLE_OUTPUT)
    findings = deps_scan.scan(tmp_path)
    licenses = [f for f in findings if f.category == "license"]
    assert len(licenses) == 1
    assert licenses[0].license_id == "AGPL"
    assert licenses[0].severity == "medium"
    assert "somelib" in licenses[0].message


def test_found_vulnerabilities_is_success_not_failure(tmp_path, monkeypatch):
    """Exit 1 just means osv-scanner found vulnerabilities — that's a normal run."""
    _patch_output(monkeypatch, SAMPLE_OUTPUT, returncode=1)
    findings = deps_scan.scan(tmp_path)
    assert findings  # parsed fine despite the non-zero exit code


def test_unparseable_output_raises_rather_than_reporting_clean(tmp_path, monkeypatch):
    """A tool that could not run must raise, never return [] — [] means "clean"."""
    _patch_output(monkeypatch, "not json", returncode=127, stderr="failed to resolve path")
    with pytest.raises(ScannerUnavailable, match="failed to resolve path"):
        deps_scan.scan(tmp_path)


def test_clean_run_with_no_results_returns_empty(tmp_path, monkeypatch):
    """A positive control: a genuinely clean run (null results) still returns []."""
    _patch_output(monkeypatch, json.dumps({"results": None}), returncode=0)
    assert deps_scan.scan(tmp_path) == []


@pytest.mark.skipif(
    _resolve_executable("osv-scanner") == "osv-scanner",
    reason="osv-scanner not installed"
)
def test_real_osv_scanner_flags_vulnerable_flask(fixture_repo):
    findings = deps_scan.scan(fixture_repo)
    security = [f for f in findings if f.category == "security"]
    assert any("flask" in f.message.lower() for f in security)
    assert all(f.tool == "osv-scanner" for f in findings)
