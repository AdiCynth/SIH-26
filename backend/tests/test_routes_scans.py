import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import routes_scans
from app.main import app
from app.models import Finding, Scan


@pytest.fixture()
def client(db, monkeypatch):
    monkeypatch.setattr(routes_scans, "run_scan", lambda scan_id: None)
    c = TestClient(app)
    c.post("/auth/signup", json={"email": "s@b.com", "password": "hunter2"})
    return c


def _zip_upload():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("app.py", "print(1)\n")
    buf.seek(0)
    return {"zip_file": ("src.zip", buf, "application/zip")}


def test_create_scan_from_repo_url(client, db):
    r = client.post("/scans", data={"repo_url": "https://github.com/Acme/Demo.git"})
    assert r.status_code == 201
    assert r.json()["status"] == "pending"
    scan = db.get(Scan, r.json()["id"])
    assert scan.repo_key == "acme/demo"
    assert scan.source_type == "git"
    assert scan.mode == "full"


def test_create_scan_from_zip(client, db):
    r = client.post("/scans", files=_zip_upload())
    assert r.status_code == 201
    scan = db.get(Scan, r.json()["id"])
    assert scan.source_type == "zip"
    assert scan.repo_key.startswith("zip:")


def test_create_scan_in_diff_mode(client, db):
    r = client.post("/scans", data={"repo_url": "https://github.com/Acme/Demo.git",
                                    "base_ref": "main", "head_ref": "feature"})
    assert r.status_code == 201
    scan = db.get(Scan, r.json()["id"])
    assert scan.mode == "diff"
    assert scan.base_ref == "main"


def test_create_scan_without_source_is_400(client):
    assert client.post("/scans", data={}).status_code == 400


def test_create_scan_with_bad_url_is_400(client):
    assert client.post("/scans", data={"repo_url": "not-a-repo"}).status_code == 400


def test_create_scan_requires_auth(db):
    anon = TestClient(app)
    assert anon.post("/scans", data={"repo_url": "https://github.com/a/b"}).status_code == 401


def test_get_scan_returns_findings(client, db):
    scan_id = client.post("/scans", data={"repo_url": "https://github.com/Acme/Demo"}).json()["id"]
    scan = db.get(Scan, scan_id)
    scan.status, scan.security_score, scan.vibe_debt_score = "done", 85, 96
    scan.findings.append(Finding(tool="semgrep", severity="high", category="security",
                                 file="app.py", line=1, message="eval",
                                 ai_explanation="Bad.", ai_fix="Remove it."))
    db.commit()

    body = client.get(f"/scans/{scan_id}").json()
    assert body["security_score"] == 85
    assert body["findings"][0]["ai_explanation"] == "Bad."


def test_cannot_read_another_users_scan(client, db):
    scan_id = client.post("/scans", data={"repo_url": "https://github.com/Acme/Demo"}).json()["id"]
    other = TestClient(app)
    other.post("/auth/signup", json={"email": "other@b.com", "password": "hunter2"})
    assert other.get(f"/scans/{scan_id}").status_code == 404


def test_list_scans_filtered_by_repo_key_for_trend(client, db):
    client.post("/scans", data={"repo_url": "https://github.com/Acme/Demo"})
    client.post("/scans", data={"repo_url": "https://github.com/Acme/Demo"})
    client.post("/scans", data={"repo_url": "https://github.com/Acme/Other"})

    assert len(client.get("/scans").json()) == 3
    assert len(client.get("/scans", params={"repo_key": "acme/demo"}).json()) == 2


def test_status_endpoint_gates_on_severity(client, db):
    scan_id = client.post("/scans", data={"repo_url": "https://github.com/Acme/Demo"}).json()["id"]
    scan = db.get(Scan, scan_id)
    scan.status, scan.security_score, scan.vibe_debt_score = "done", 85, 96
    scan.findings.append(Finding(tool="semgrep", severity="high", category="security",
                                 file="app.py", line=1, message="eval"))
    db.commit()

    assert client.get(f"/scans/{scan_id}/status", params={"fail_on": "high"}).json()["passed"] is False
    assert client.get(f"/scans/{scan_id}/status", params={"fail_on": "critical"}).json()["passed"] is True


def test_status_endpoint_rejects_bad_severity(client, db):
    scan_id = client.post("/scans", data={"repo_url": "https://github.com/Acme/Demo"}).json()["id"]
    r = client.get(f"/scans/{scan_id}/status", params={"fail_on": "spicy"})
    assert r.status_code == 422
