import pytest

from app.scanners.base import (RawFinding, ScannerUnavailable,
                               normalize_severity, run_tool)


def test_raw_finding_defaults():
    finding = RawFinding(tool="semgrep", severity="high", file="a.py",
                         line=3, message="bad")
    assert finding.category == "security"
    assert finding.license_id is None


@pytest.mark.parametrize(
    "raw,expected",
    [("ERROR", "high"), ("WARNING", "medium"), ("INFO", "info"),
     ("CRITICAL", "critical"), ("Moderate", "medium"), ("nonsense", "medium")],
)
def test_normalize_severity(raw, expected):
    assert normalize_severity(raw) == expected


def test_run_tool_captures_output(tmp_path):
    result = run_tool(["echo", "hello"], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == "hello"


def test_run_tool_raises_when_binary_missing(tmp_path):
    with pytest.raises(ScannerUnavailable):
        run_tool(["definitely-not-a-real-binary-xyz"], cwd=tmp_path)


def test_fixture_repo_is_present(fixture_repo):
    assert (fixture_repo / "config.py").exists()
    assert (fixture_repo / "requirements.txt").read_text().strip() == "flask==0.12.2"
