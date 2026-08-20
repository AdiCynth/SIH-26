"""End-to-end check from the spec: a repo with a planted secret, a vulnerable
dependency, and duplicated code must produce all three finding kinds.

This is the one test in the suite that runs the REAL scanners against the REAL
fixture repo. Everything else mocks at the boundary; this test is the backstop
that catches wiring breaks unit tests can't see."""

import shutil

import pytest

from app import pipeline
from app.models import Scan, User
from app.scanners.base import _resolve_executable


@pytest.fixture()
def scan_of_fixture(db, fixture_repo, tmp_path):
    workspace = tmp_path / "repo"
    shutil.copytree(fixture_repo, workspace)
    user = User(email="e2e@b.com", password_hash="x")
    db.add(user)
    db.flush()
    scan = Scan(user_id=user.id, repo_key="acme/vulnerable", mode="full",
                status="pending", source_type="local", source_ref=str(workspace))
    db.add(scan)
    db.commit()
    return scan


def test_pipeline_reports_secrets_vulns_and_vibe_debt(db, scan_of_fixture, monkeypatch):
    # No API key in tests: the AI layer degrades, the report still ships.
    monkeypatch.setattr(pipeline, "annotate", lambda findings: None)

    pipeline.run_scan(scan_of_fixture.id)

    db.expire_all()
    scan = db.get(Scan, scan_of_fixture.id)
    assert scan.status == "done", f"scan failed: {scan.error}"

    tools = {f.tool for f in scan.findings}
    categories = {f.category for f in scan.findings}

    assert "lizard" in tools, "vibe debt scanner produced nothing"
    assert "vibe-debt" in categories
    assert any("duplicate" in f.message.lower() for f in scan.findings)

    assert "semgrep" in tools, "semgrep produced nothing"
    assert any(
        f.tool == "semgrep" and f.file == "app.py" and "eval" in f.message.lower()
        for f in scan.findings
    ), "semgrep missed the eval() injection in app.py"

    if _resolve_executable("gitleaks") != "gitleaks":
        assert any(f.tool == "gitleaks" for f in scan.findings), "planted secret missed"
    if shutil.which("dependency-check.sh"):
        assert any("flask" in f.message.lower() for f in scan.findings), \
            "vulnerable flask dependency missed"

    # On a machine without dependency-check.sh, that scanner is expected to fail —
    # and a scanner that cannot run must be named in scan.error, not silently
    # dropped. Guarded like the positive assertions above: installing the tool per
    # the README must not start failing this test.
    if not shutil.which("dependency-check.sh"):
        assert scan.error is not None
        assert "depcheck_scan" in scan.error or "dependency-check" in scan.error

    # Three of four scanners ran for real: partial failure must not sink the scan.
    assert scan.status == "done"

    assert scan.security_score is not None
    assert scan.vibe_debt_score is not None
    assert scan.security_score < 100, "real findings exist; a perfect score means scoring isn't wired up"
    assert scan.vibe_debt_score < 100, "duplicated code should cost vibe debt points"
    assert scan.ai_available is False
