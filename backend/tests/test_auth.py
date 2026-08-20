import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password, verify_password
from app.main import app


@pytest.fixture()
def client(db):
    return TestClient(app)


def test_password_hash_round_trip():
    hashed = hash_password("hunter2")
    assert hashed != "hunter2"
    assert verify_password("hunter2", hashed)
    assert not verify_password("wrong", hashed)


def test_signup_then_me(client):
    r = client.post("/auth/signup", json={"email": "a@b.com", "password": "hunter2"})
    assert r.status_code == 201
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "a@b.com"


def test_duplicate_signup_rejected(client):
    client.post("/auth/signup", json={"email": "dup@b.com", "password": "hunter2"})
    r = client.post("/auth/signup", json={"email": "dup@b.com", "password": "hunter2"})
    assert r.status_code == 409


def test_login_wrong_password_rejected(client):
    client.post("/auth/signup", json={"email": "c@b.com", "password": "hunter2"})
    client.post("/auth/logout")
    r = client.post("/auth/login", json={"email": "c@b.com", "password": "nope"})
    assert r.status_code == 401


def test_me_without_cookie_is_401(client):
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


# --- Deployment-shaped config: both of these only bite off localhost. ---

def test_cookie_is_lax_and_insecure_for_same_site_local_dev(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cookie_cross_site", False)
    r = client.post("/auth/signup", json={"email": "lax@b.com", "password": "hunter2"})
    header = r.headers["set-cookie"].lower()
    assert "samesite=lax" in header
    assert "secure" not in header


def test_cookie_is_none_and_secure_when_cross_site(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cookie_cross_site", True)
    r = client.post("/auth/signup", json={"email": "xsite@b.com", "password": "hunter2"})
    header = r.headers["set-cookie"].lower()
    assert "samesite=none" in header
    assert "secure" in header, "SameSite=None without Secure is dropped by the browser"


def test_startup_refuses_the_default_jwt_secret_off_localhost():
    from app.config import DEFAULT_JWT_SECRET, Settings, check_production_secrets

    remote = Settings(jwt_secret=DEFAULT_JWT_SECRET, frontend_url="https://vibeguard.example.com")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        check_production_secrets(remote)


def test_startup_allows_the_default_jwt_secret_on_localhost():
    from app.config import DEFAULT_JWT_SECRET, Settings, check_production_secrets

    local = Settings(jwt_secret=DEFAULT_JWT_SECRET, frontend_url="http://localhost:3000")
    check_production_secrets(local)  # must not raise

    remote_but_configured = Settings(jwt_secret="a-real-secret",
                                     frontend_url="https://vibeguard.example.com")
    check_production_secrets(remote_but_configured)  # must not raise
