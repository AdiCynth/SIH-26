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
