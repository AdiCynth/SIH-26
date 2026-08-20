from urllib.parse import parse_qs, urlsplit

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


def _start_login(client) -> str:
    """Walk the real /auth/github/login leg so the state cookie is set, and return
    the state GitHub would echo back."""
    r = client.get("/auth/github/login", follow_redirects=False)
    return parse_qs(urlsplit(r.headers["location"]).query)["state"][0]


def test_login_redirects_to_github(client):
    r = client.get("/auth/github/login", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://github.com/login/oauth/authorize")
    assert "client_id=test-client-id" in r.headers["location"]
    assert "state=" in r.headers["location"]
    assert "vibeguard_oauth_state" in r.headers["set-cookie"]


def test_callback_creates_user_and_sets_cookie(client, db, monkeypatch):
    monkeypatch.setattr(
        routes_auth, "exchange_code",
        lambda code: {"github_id": "4242", "email": "octo@github.com"},
    )
    state = _start_login(client)
    r = client.get(f"/auth/github/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == settings.frontend_url
    assert client.get("/auth/me").json()["email"] == "octo@github.com"
    assert db.query(User).filter(User.github_id == "4242").count() == 1


def test_callback_reuses_existing_github_user(client, db, monkeypatch):
    monkeypatch.setattr(
        routes_auth, "exchange_code",
        lambda code: {"github_id": "4242", "email": "octo@github.com"},
    )
    client.get(f"/auth/github/callback?code=abc&state={_start_login(client)}",
               follow_redirects=False)
    client.get(f"/auth/github/callback?code=def&state={_start_login(client)}",
               follow_redirects=False)
    assert db.query(User).filter(User.github_id == "4242").count() == 1


def test_callback_links_to_existing_password_account(client, db, monkeypatch):
    from app.auth import hash_password

    # Create an existing password account
    existing_user = User(email="octo@github.com", password_hash=hash_password("hunter2!"))
    db.add(existing_user)
    db.commit()
    original_password_hash = existing_user.password_hash

    # GitHub login with the same email
    monkeypatch.setattr(
        routes_auth, "exchange_code",
        lambda code: {"github_id": "4242", "email": "octo@github.com"},
    )
    state = _start_login(client)
    r = client.get(f"/auth/github/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == settings.frontend_url

    # Should still have only one user, with github_id now set
    user = db.query(User).filter(User.email == "octo@github.com").first()
    assert user is not None
    assert user.github_id == "4242"
    # Password hash should be unchanged
    assert user.password_hash == original_password_hash


def test_exchange_code_rejects_unverified_email(monkeypatch):
    import httpx

    from app.routes_auth import exchange_code

    # Mock httpx.Client to simulate GitHub API responses
    class MockResponse:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

        def raise_for_status(self):
            pass

    def mock_post(self, url, **kwargs):
        return MockResponse({"access_token": "test-token"})

    def mock_get(self, url, **kwargs):
        if "/user/emails" in url:
            # Return unverified email as primary
            return MockResponse([
                {"email": "victim@example.com", "primary": True, "verified": False}
            ])
        else:
            # Return profile with ID
            return MockResponse({"id": 4242})

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    monkeypatch.setattr(httpx.Client, "get", mock_get)

    result = exchange_code("test-code")

    # Should fall back to noreply address since the primary email is unverified
    assert result["github_id"] == "4242"
    assert result["email"] == "4242@users.noreply.github.com"
    assert result["email"] != "victim@example.com"


def test_exchange_code_raises_on_rejected_code(monkeypatch):
    import httpx

    from app.routes_auth import exchange_code

    class MockResponse:
        def json(self):
            # GitHub rejected the code: no access_token
            return {}

        def raise_for_status(self):
            pass

    def mock_post(self, url, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        exchange_code("invalid-code")

    assert exc_info.value.status_code == 401
    assert "rejected" in exc_info.value.detail.lower()


# --- CSRF: without state, an attacker can log a victim into the attacker's account. ---

def test_callback_without_state_is_rejected(client, db, monkeypatch):
    monkeypatch.setattr(routes_auth, "exchange_code",
                        lambda code: {"github_id": "9", "email": "attacker@github.com"})
    r = client.get("/auth/github/callback?code=abc", follow_redirects=False)
    assert r.status_code == 400
    assert db.query(User).count() == 0


def test_callback_with_mismatched_state_is_rejected(client, db, monkeypatch):
    monkeypatch.setattr(routes_auth, "exchange_code",
                        lambda code: {"github_id": "9", "email": "attacker@github.com"})
    _start_login(client)  # sets a real state cookie
    r = client.get("/auth/github/callback?code=abc&state=forged", follow_redirects=False)
    assert r.status_code == 400
    assert db.query(User).count() == 0


def test_callback_state_is_single_use(client, db, monkeypatch):
    monkeypatch.setattr(routes_auth, "exchange_code",
                        lambda code: {"github_id": "4242", "email": "octo@github.com"})
    state = _start_login(client)
    assert client.get(f"/auth/github/callback?code=abc&state={state}",
                      follow_redirects=False).status_code == 307
    replayed = client.get(f"/auth/github/callback?code=abc&state={state}",
                          follow_redirects=False)
    assert replayed.status_code == 400


def test_github_api_failure_becomes_502_not_a_traceback(monkeypatch):
    import httpx

    from app.routes_auth import exchange_code

    class MockResponse:
        def __init__(self, data=None, fail=False):
            self._data, self._fail = data, fail

        def json(self):
            return self._data

        def raise_for_status(self):
            if self._fail:
                raise httpx.HTTPStatusError("503", request=None, response=None)

    monkeypatch.setattr(httpx.Client, "post",
                        lambda self, url, **kw: MockResponse({"access_token": "t"}))
    monkeypatch.setattr(httpx.Client, "get",
                        lambda self, url, **kw: MockResponse(fail=True))

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        exchange_code("code")
    assert exc_info.value.status_code == 502
