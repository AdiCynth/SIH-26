from app.models import Finding, Scan, User


def test_scan_with_findings_round_trips(db):
    user = User(email="dev@example.com", password_hash="x")
    db.add(user)
    db.flush()

    scan = Scan(user_id=user.id, repo_key="acme/demo", mode="full", status="done",
                security_score=72, vibe_debt_score=85,
                source_type="git", source_ref="https://github.com/acme/demo")
    scan.findings.append(
        Finding(tool="gitleaks", severity="high", file="config.py", line=3,
                message="AWS key committed", category="security")
    )
    db.add(scan)
    db.commit()

    loaded = db.query(Scan).one()
    assert loaded.status == "done"
    assert loaded.security_score == 72
    assert len(loaded.findings) == 1
    assert loaded.findings[0].tool == "gitleaks"
    assert loaded.findings[0].ai_explanation is None
