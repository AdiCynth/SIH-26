import pytest
from fastapi.testclient import TestClient

from app import routes_auth
from app.config import settings
from app.main import app
from app.models import User


@pytest.fixture()
def client(db):
    settings.github_client_id = "test-client-id"
    settings.github_client_secret = "test-secret"
    return TestClient(app)


def test_login_redirects_to_github(client):
    r = client.get("/auth/github/login", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://github.com/login/oauth/authorize")
    assert "client_id=test-client-id" in r.headers["location"]


def test_callback_creates_user_and_sets_cookie(client, db, monkeypatch):
    monkeypatch.setattr(
        routes_auth, "exchange_code",
        lambda code: {"github_id": "4242", "email": "octo@github.com"},
    )
    r = client.get("/auth/github/callback?code=abc", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == settings.frontend_url
    assert client.get("/auth/me").json()["email"] == "octo@github.com"
    assert db.query(User).filter(User.github_id == "4242").count() == 1


def test_callback_reuses_existing_github_user(client, db, monkeypatch):
    monkeypatch.setattr(
        routes_auth, "exchange_code",
        lambda code: {"github_id": "4242", "email": "octo@github.com"},
    )
    client.get("/auth/github/callback?code=abc", follow_redirects=False)
    client.get("/auth/github/callback?code=def", follow_redirects=False)
    assert db.query(User).filter(User.github_id == "4242").count() == 1
