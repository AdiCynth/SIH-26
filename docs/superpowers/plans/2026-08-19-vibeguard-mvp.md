# VibeGuard MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the VibeGuard core scan pipeline — a user logs in, submits a repo (GitHub URL, zip, or diff range), deterministic scanners find security/dependency/complexity issues, an OpenAI reasoning layer explains and prioritizes them, and the user gets a scored, actionable report with a score trend across rescans.

**Architecture:** A FastAPI backend owns everything server-side: auth (email/password + GitHub OAuth), repo intake into a temp workspace, a set of independent scanner modules that each shell out to a CLI tool and return a common `RawFinding` shape, an OpenAI reasoning pass over those findings, a scoring step, and persistence to Postgres. Scans run in a FastAPI `BackgroundTasks` job that flips a status column; the Next.js frontend polls until done and renders the report.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Postgres (SQLite in tests), PyJWT, bcrypt, httpx, OpenAI Python SDK, Semgrep, Gitleaks, OWASP Dependency-Check, lizard; Next.js (App Router) + TypeScript + Tailwind.

**Spec:** `docs/superpowers/specs/2026-08-19-vibeguard-mvp-design.md`

## Global Constraints

- Python 3.11+. Node 20+.
- The AI layer **never invents findings**. It only annotates findings that a deterministic tool already produced. Every prompt in this plan passes findings in and asks only for explanation/fix/priority back.
- If the OpenAI call fails, the scan still completes. `ai_explanation`/`ai_fix` stay `NULL` and the UI shows "unavailable".
- A scan is marked `failed` **only if every scanner failed**. If at least one produced output, the scan completes with partial findings.
- The intake workspace is always deleted, success or failure (`try/finally`).
- Scanning is language-agnostic — no language gating in our code. Semgrep/Gitleaks/lizard run over whatever is there; Dependency-Check only fires on manifests it recognizes, which is inherent to that tool.
- Severity vocabulary is exactly: `critical`, `high`, `medium`, `low`, `info`.
- Finding category vocabulary is exactly: `security`, `vibe-debt`, `license`.
- Scan status vocabulary is exactly: `pending`, `running`, `done`, `failed`.
- All commits end with the line `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Backend runs on `http://localhost:8000`, frontend on `http://localhost:3000`. Both are `localhost`, so they are same-site and a `SameSite=Lax` cookie works.

### Deviation from the spec (deliberate, flagged)

The spec derives the Vibe Debt score from "Semgrep complexity/duplicate-code rule findings". Semgrep's public registry has almost no cross-language complexity or duplicate-detection rules, so that path would produce an empty score. This plan uses **lizard** (pip package, Python API, ~15 languages) for cyclomatic complexity and long functions, plus a normalized-body hash for duplicate detection. Same output, same score, a tool that actually does the job.

## File Structure

```
backend/
  requirements.txt
  .env.example
  app/
    __init__.py
    config.py          # env-backed settings singleton
    db.py              # engine, SessionLocal, init_db()
    models.py          # User, Scan, Finding
    auth.py            # password hashing, JWT, current-user dependency
    routes_auth.py     # signup/login/logout/me + GitHub OAuth
    intake.py          # git clone / zip extract / diff file list, repo_key
    scanners/
      __init__.py
      base.py          # RawFinding, run_tool()
      semgrep_scan.py
      gitleaks_scan.py
      depcheck_scan.py
      lizard_scan.py
    reasoning.py       # OpenAI annotation pass
    scoring.py         # security_score(), vibe_debt_score()
    pipeline.py        # run_scan() orchestration
    routes_scans.py    # POST /scans, GET /scans, GET /scans/{id}, /status
    main.py            # app assembly, CORS, router mounting
  tests/
    conftest.py
    fixtures/vulnerable_repo/   # planted secret, vulnerable dep, dup code
    test_models.py
    test_auth.py
    test_oauth.py
    test_intake.py
    test_scanner_base.py
    test_semgrep_scan.py
    test_gitleaks_scan.py
    test_depcheck_scan.py
    test_lizard_scan.py
    test_scoring.py
    test_reasoning.py
    test_pipeline.py
    test_routes_scans.py
    test_scan_pipeline.py       # end-to-end, the spec's required check
frontend/
  app/
    layout.tsx
    page.tsx              # dashboard: submit form + past scans
    login/page.tsx
    signup/page.tsx
    scans/[id]/page.tsx   # report view + trend
  lib/api.ts              # fetch wrapper, typed responses
  components/
    ScoreBadge.tsx
    Sparkline.tsx
    FindingCard.tsx
```

Each scanner module is self-contained and exposes the same `scan(workspace, files)` signature, so `pipeline.py` treats them as a list. That shape is justified by four real implementations, not speculation.

---

### Task 1: Project skeleton, config, database models

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py` (empty)
- Create: `backend/app/config.py`
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `app.config.settings` — object with attributes `database_url: str`, `jwt_secret: str`, `openai_api_key: str`, `openai_model: str`, `github_client_id: str`, `github_client_secret: str`, `frontend_url: str`
  - `app.db.engine`, `app.db.SessionLocal`, `app.db.init_db() -> None`, `app.db.get_db()` (FastAPI dependency yielding a `Session`)
  - `app.models.Base`, `app.models.User`, `app.models.Scan`, `app.models.Finding`

- [ ] **Step 1: Create dependency and env files**

`backend/requirements.txt`:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.0.36
psycopg[binary]==3.2.3
pydantic-settings==2.7.0
python-multipart==0.0.20
pyjwt==2.10.1
bcrypt==4.2.1
httpx==0.28.1
openai==1.59.6
lizard==1.17.10
semgrep==1.101.0
pytest==8.3.4
```

`backend/.env.example`:

```
DATABASE_URL=postgresql+psycopg://vibeguard:vibeguard@localhost:5432/vibeguard
JWT_SECRET=change-me-in-production
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
FRONTEND_URL=http://localhost:3000
```

- [ ] **Step 2: Write the failing test**

`backend/tests/conftest.py`:

```python
import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway SQLite file before app modules import settings.
_TMP_DB = Path(tempfile.mkdtemp(prefix="vibeguard-test-")) / "test.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{_TMP_DB}")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.db import SessionLocal, engine, init_db  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def fixture_repo() -> Path:
    return Path(__file__).parent / "fixtures" / "vulnerable_repo"
```

`backend/tests/test_models.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 4: Write config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://vibeguard:vibeguard@localhost:5432/vibeguard"
    jwt_secret: str = "dev-secret-change-me"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    github_client_id: str = ""
    github_client_secret: str = ""
    frontend_url: str = "http://localhost:3000"


settings = Settings()
```

- [ ] **Step 5: Write models.py**

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    github_id: Mapped[str | None] = mapped_column(String(64), unique=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    repo_key: Mapped[str] = mapped_column(String(255), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="full")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    security_score: Mapped[int | None] = mapped_column(Integer, default=None)
    vibe_debt_score: Mapped[int | None] = mapped_column(Integer, default=None)
    ai_available: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    # How to fetch the code at scan time.
    source_type: Mapped[str] = mapped_column(String(8), default="git")  # git | zip
    source_ref: Mapped[str] = mapped_column(Text)  # clone URL, or temp zip path
    base_ref: Mapped[str | None] = mapped_column(String(255), default=None)
    head_ref: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    findings: Mapped[list["Finding"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), index=True)
    tool: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(16), default="security")
    file: Mapped[str] = mapped_column(Text)
    line: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text)
    license_id: Mapped[str | None] = mapped_column(String(64), default=None)
    ai_explanation: Mapped[str | None] = mapped_column(Text, default=None)
    ai_fix: Mapped[str | None] = mapped_column(Text, default=None)

    scan: Mapped["Scan"] = relationship(back_populates="findings")
```

- [ ] **Step 6: Write db.py**

```python
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create tables. No migration tool for the MVP — the schema is new."""
    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: project skeleton, settings, and database models"
```

---

### Task 2: Email/password auth

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/app/routes_auth.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `app.models.User`, `app.db.get_db`, `app.config.settings`
- Produces:
  - `app.auth.hash_password(plain: str) -> str`
  - `app.auth.verify_password(plain: str, hashed: str) -> bool`
  - `app.auth.create_token(user_id: int) -> str`
  - `app.auth.set_auth_cookie(response, token: str) -> None`
  - `app.auth.current_user(request, db) -> User` — FastAPI dependency, raises 401
  - `app.routes_auth.router` — `POST /auth/signup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`
  - `app.main.app` — the FastAPI application

- [ ] **Step 1: Write the failing test**

`backend/tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: Write auth.py**

```python
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

COOKIE_NAME = "vibeguard_session"
TOKEN_TTL = timedelta(days=7)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.now(UTC) + TOKEN_TTL}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax",
        max_age=int(TOKEN_TTL.total_seconds()), path="/",
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user
```

- [ ] **Step 4: Write routes_auth.py**

```python
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth import (COOKIE_NAME, create_token, current_user, hash_password,
                      set_auth_cookie, verify_password)
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str


@router.post("/signup", status_code=201, response_model=UserOut)
def signup(body: Credentials, response: Response, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    set_auth_cookie(response, create_token(user.id))
    return UserOut(id=user.id, email=user.email)


@router.post("/login", response_model=UserOut)
def login(body: Credentials, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not user.password_hash or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    set_auth_cookie(response, create_token(user.id))
    return UserOut(id=user.id, email=user.email)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(id=user.id, email=user.email)
```

`EmailStr` needs the extra: add `email-validator==2.2.0` to `backend/requirements.txt` and install it.

- [ ] **Step 5: Write main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import routes_auth
from app.config import settings
from app.db import init_db

app = FastAPI(title="VibeGuard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_auth.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: email/password auth with JWT session cookie"
```

---

### Task 3: GitHub OAuth login

**Files:**
- Modify: `backend/app/routes_auth.py` (append the two OAuth routes)
- Test: `backend/tests/test_oauth.py`

**Interfaces:**
- Consumes: `app.auth.create_token`, `app.auth.set_auth_cookie`, `app.models.User`
- Produces: `GET /auth/github/login` (302 to GitHub), `GET /auth/github/callback?code=` (302 to frontend, sets cookie)
- Produces: `app.routes_auth.exchange_code(code: str) -> dict` — returns `{"github_id": str, "email": str}`; separated so tests can monkeypatch it

- [ ] **Step 1: Write the failing test**

`backend/tests/test_oauth.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_oauth.py -v`
Expected: FAIL — `/auth/github/login` returns 404

- [ ] **Step 3: Append the OAuth routes to routes_auth.py**

Add these imports at the top of the existing file:

```python
import httpx
from fastapi import Request
from fastapi.responses import RedirectResponse

from app.config import settings
```

Append to the end of `routes_auth.py`:

```python
GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com"


def exchange_code(code: str) -> dict:
    """Trade an OAuth code for the GitHub account's id and email."""
    with httpx.Client(timeout=15) as http:
        token_resp = http.post(
            GITHUB_TOKEN,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=401, detail="GitHub rejected the code")

        headers = {"Authorization": f"Bearer {access_token}",
                   "Accept": "application/vnd.github+json"}
        profile = http.get(f"{GITHUB_API}/user", headers=headers).json()
        email = profile.get("email")
        if not email:
            emails = http.get(f"{GITHUB_API}/user/emails", headers=headers).json()
            primary = next((e for e in emails if e.get("primary")), None)
            email = primary["email"] if primary else f"{profile['id']}@users.noreply.github.com"
        return {"github_id": str(profile["id"]), "email": email}


@router.get("/github/login")
def github_login(request: Request):
    redirect_uri = str(request.url_for("github_callback"))
    return RedirectResponse(
        f"{GITHUB_AUTHORIZE}?client_id={settings.github_client_id}"
        f"&redirect_uri={redirect_uri}&scope=read:user%20user:email"
    )


@router.get("/github/callback", name="github_callback")
def github_callback(code: str, db: Session = Depends(get_db)):
    account = exchange_code(code)
    user = db.query(User).filter(User.github_id == account["github_id"]).first()
    if user is None:
        # An existing email/password account with the same address gets linked.
        user = db.query(User).filter(User.email == account["email"]).first()
        if user is None:
            user = User(email=account["email"])
            db.add(user)
        user.github_id = account["github_id"]
        db.commit()
    response = RedirectResponse(settings.frontend_url)
    set_auth_cookie(response, create_token(user.id))
    return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_oauth.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS (all tests so far)

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: GitHub OAuth login"
```

---

### Task 4: Repo intake (clone, unzip, diff file list)

**Files:**
- Create: `backend/app/intake.py`
- Test: `backend/tests/test_intake.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - `app.intake.Workspace` — dataclass with `path: Path` and `files: list[str] | None` (None means "scan everything")
  - `app.intake.prepare(source_type: str, source_ref: str, base_ref: str | None = None, head_ref: str | None = None)` — context manager yielding `Workspace`, always deletes the temp dir
  - `app.intake.repo_key_from_url(url: str) -> str` — e.g. `"acme/demo"`
  - `app.intake.repo_key_from_bytes(data: bytes) -> str` — e.g. `"zip:1a2b3c4d5e6f7a8b"`
  - `app.intake.IntakeError` — raised for bad input; routes turn it into a 400

- [ ] **Step 1: Write the failing test**

`backend/tests/test_intake.py`:

```python
import io
import zipfile
from pathlib import Path

import pytest

from app.intake import (IntakeError, prepare, repo_key_from_bytes,
                        repo_key_from_url)


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_repo_key_from_url_normalizes():
    assert repo_key_from_url("https://github.com/Acme/Demo.git") == "acme/demo"
    assert repo_key_from_url("https://github.com/Acme/Demo/") == "acme/demo"


def test_repo_key_from_bytes_is_stable():
    assert repo_key_from_bytes(b"hello") == repo_key_from_bytes(b"hello")
    assert repo_key_from_bytes(b"hello") != repo_key_from_bytes(b"world")
    assert repo_key_from_bytes(b"hello").startswith("zip:")


def test_zip_intake_extracts_and_cleans_up(tmp_path):
    zip_path = tmp_path / "src.zip"
    zip_path.write_bytes(_zip_bytes({"app.py": "print(1)\n"}))

    with prepare("zip", str(zip_path)) as ws:
        workspace = ws.path
        assert (workspace / "app.py").read_text() == "print(1)\n"
        assert ws.files is None
    assert not workspace.exists()


def test_zip_slip_is_rejected(tmp_path):
    zip_path = tmp_path / "evil.zip"
    zip_path.write_bytes(_zip_bytes({"../escaped.py": "pwned"}))

    with pytest.raises(IntakeError):
        with prepare("zip", str(zip_path)):
            pass
    assert not (tmp_path.parent / "escaped.py").exists()


def test_unknown_source_type_rejected():
    with pytest.raises(IntakeError):
        with prepare("carrier-pigeon", "somewhere"):
            pass


def test_diff_mode_lists_only_changed_files(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *args: subprocess.run(args, cwd=repo, check=True, capture_output=True)
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@t.com")
    run("git", "config", "user.name", "t")
    (repo / "kept.py").write_text("a = 1\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "base")
    (repo / "changed.py").write_text("b = 2\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "head")

    with prepare("git", str(repo), base_ref="HEAD~1", head_ref="HEAD") as ws:
        assert ws.files == ["changed.py"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_intake.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.intake'`

- [ ] **Step 3: Write intake.py**

```python
import hashlib
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class IntakeError(Exception):
    """Bad or unusable source input. Callers map this to HTTP 400."""


@dataclass
class Workspace:
    path: Path
    files: list[str] | None  # None means "scan the whole tree"


def repo_key_from_url(url: str) -> str:
    match = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not match:
        raise IntakeError(f"Could not parse a repository name from {url!r}")
    return f"{match.group(1).lower()}/{match.group(2).lower()}"


def repo_key_from_bytes(data: bytes) -> str:
    return f"zip:{hashlib.sha256(data).hexdigest()[:16]}"


def _clone(url: str, dest: Path) -> None:
    result = subprocess.run(
        ["git", "clone", "--quiet", url, str(dest)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise IntakeError(f"Could not clone repository: {result.stderr.strip()[:200]}")


def _extract(zip_path: str, dest: Path) -> None:
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, FileNotFoundError) as exc:
        raise IntakeError("Uploaded file is not a readable zip archive") from exc
    with archive:
        for member in archive.namelist():
            target = (dest / member).resolve()
            # Zip-slip guard: a member must not escape the workspace.
            if not str(target).startswith(str(dest.resolve())):
                raise IntakeError(f"Archive entry escapes the workspace: {member!r}")
        archive.extractall(dest)


def _changed_files(repo: Path, base_ref: str, head_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        cwd=repo, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise IntakeError(f"Could not diff {base_ref}...{head_ref}: {result.stderr.strip()[:200]}")
    return [line for line in result.stdout.splitlines() if (repo / line).exists()]


@contextmanager
def prepare(
    source_type: str,
    source_ref: str,
    base_ref: str | None = None,
    head_ref: str | None = None,
) -> Iterator[Workspace]:
    """Materialize the code under scan in a temp dir, always cleaned up."""
    workspace = Path(tempfile.mkdtemp(prefix="vibeguard-"))
    try:
        if source_type == "git":
            source = Path(source_ref)
            if source.is_dir():
                shutil.copytree(source, workspace, dirs_exist_ok=True)
            else:
                _clone(source_ref, workspace)
        elif source_type == "zip":
            _extract(source_ref, workspace)
        else:
            raise IntakeError(f"Unknown source type {source_type!r}")

        files = None
        if base_ref and head_ref:
            files = _changed_files(workspace, base_ref, head_ref)
        yield Workspace(path=workspace, files=files)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_intake.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: repo intake via clone, zip, or diff range"
```

---

### Task 5: Scanner base + shared test fixture repo

**Files:**
- Create: `backend/app/scanners/__init__.py` (empty)
- Create: `backend/app/scanners/base.py`
- Create: `backend/tests/fixtures/vulnerable_repo/config.py`
- Create: `backend/tests/fixtures/vulnerable_repo/app.py`
- Create: `backend/tests/fixtures/vulnerable_repo/dup.py`
- Create: `backend/tests/fixtures/vulnerable_repo/requirements.txt`
- Test: `backend/tests/test_scanner_base.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - `app.scanners.base.RawFinding` — dataclass: `tool: str`, `severity: str`, `file: str`, `line: int`, `message: str`, `category: str = "security"`, `license_id: str | None = None`
  - `app.scanners.base.run_tool(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess`
  - `app.scanners.base.ScannerUnavailable` — raised when the CLI is not installed
  - `app.scanners.base.normalize_severity(raw: str) -> str` — maps tool vocabularies onto ours
  - `backend/tests/fixtures/vulnerable_repo/` — the shared fixture every scanner test uses

- [ ] **Step 1: Create the fixture repo**

`backend/tests/fixtures/vulnerable_repo/config.py` — a committed AWS credential for Gitleaks:

```python
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
DEBUG = True
```

`backend/tests/fixtures/vulnerable_repo/app.py` — injection patterns for Semgrep:

```python
import subprocess

from flask import Flask, request

app = Flask(__name__)


@app.route("/calc")
def calc():
    return str(eval(request.args["expr"]))


@app.route("/ping")
def ping():
    host = request.args["host"]
    return subprocess.check_output(f"ping -c 1 {host}", shell=True)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
```

`backend/tests/fixtures/vulnerable_repo/requirements.txt` — a dependency with known CVEs:

```
flask==0.12.2
```

`backend/tests/fixtures/vulnerable_repo/dup.py` — duplicate bodies plus one gnarly function for lizard:

```python
def summarize_orders(orders):
    total = 0
    count = 0
    for order in orders:
        total += order["amount"]
        count += 1
    average = total / count if count else 0
    return {"total": total, "count": count, "average": average}


def summarize_refunds(refunds):
    total = 0
    count = 0
    for order in refunds:
        total += order["amount"]
        count += 1
    average = total / count if count else 0
    return {"total": total, "count": count, "average": average}


def classify(value, mode, flag, extra):
    if mode == "a":
        if flag:
            if extra > 10:
                return "a-flag-high"
            elif extra > 5:
                return "a-flag-mid"
            else:
                return "a-flag-low"
        elif value > 100:
            return "a-big"
        else:
            return "a-small"
    elif mode == "b":
        if flag and extra:
            return "b-both"
        elif flag or extra:
            return "b-either"
        elif value < 0:
            return "b-negative"
        else:
            return "b-plain"
    elif mode == "c":
        return "c-high" if value > 50 else "c-low"
    return "unknown"
```

- [ ] **Step 2: Write the failing test**

`backend/tests/test_scanner_base.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_scanner_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.scanners'`

- [ ] **Step 4: Write scanners/base.py**

```python
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ScannerUnavailable(Exception):
    """The tool's CLI is not installed on this machine."""


@dataclass
class RawFinding:
    tool: str
    severity: str
    file: str
    line: int
    message: str
    category: str = "security"
    license_id: str | None = None


_SEVERITY_MAP = {
    "critical": "critical",
    "error": "high", "high": "high",
    "warning": "medium", "medium": "medium", "moderate": "medium",
    "low": "low", "minor": "low",
    "info": "info", "note": "info", "informational": "info",
}


def normalize_severity(raw: str) -> str:
    """Map a tool's severity vocabulary onto ours; unknown values are medium."""
    return _SEVERITY_MAP.get((raw or "").strip().lower(), "medium")


def run_tool(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise ScannerUnavailable(f"{cmd[0]} is not installed") from exc
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_scanner_base.py -v`
Expected: PASS (9 tests, counting the parametrized cases)

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: scanner base types and shared vulnerable test fixture"
```

---

### Task 6: Semgrep scanner

**Files:**
- Create: `backend/app/scanners/semgrep_scan.py`
- Test: `backend/tests/test_semgrep_scan.py`

**Interfaces:**
- Consumes: `app.scanners.base.RawFinding`, `run_tool`, `normalize_severity`, `ScannerUnavailable`
- Produces: `app.scanners.semgrep_scan.scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]` — the signature every scanner module shares

- [ ] **Step 1: Write the failing test**

`backend/tests/test_semgrep_scan.py`:

```python
import json
import shutil

import pytest

from app.scanners import semgrep_scan
from app.scanners.base import ScannerUnavailable

SAMPLE_OUTPUT = json.dumps({
    "results": [
        {
            "check_id": "python.lang.security.audit.eval-detected",
            "path": "app.py",
            "start": {"line": 11},
            "extra": {"severity": "ERROR", "message": "Detected eval on user input"},
        },
        {
            "check_id": "python.flask.debug-enabled",
            "path": "app.py",
            "start": {"line": 22},
            "extra": {"severity": "WARNING", "message": "Flask debug mode enabled"},
        },
    ]
})


def test_parses_results_into_findings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        semgrep_scan, "run_tool",
        lambda cmd, cwd, timeout=600: type(
            "R", (), {"returncode": 0, "stdout": SAMPLE_OUTPUT, "stderr": ""}
        )(),
    )
    findings = semgrep_scan.scan(tmp_path)
    assert len(findings) == 2
    assert findings[0].tool == "semgrep"
    assert findings[0].severity == "high"
    assert findings[0].category == "security"
    assert findings[0].file == "app.py"
    assert findings[0].line == 11
    assert "eval" in findings[0].message
    assert findings[1].severity == "medium"


def test_unparseable_output_yields_no_findings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        semgrep_scan, "run_tool",
        lambda cmd, cwd, timeout=600: type(
            "R", (), {"returncode": 2, "stdout": "not json", "stderr": "boom"}
        )(),
    )
    assert semgrep_scan.scan(tmp_path) == []


def test_diff_mode_passes_only_changed_files(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, cwd, timeout=600):
        captured["cmd"] = cmd
        return type("R", (), {"returncode": 0, "stdout": '{"results": []}', "stderr": ""})()

    monkeypatch.setattr(semgrep_scan, "run_tool", fake_run)
    semgrep_scan.scan(tmp_path, files=["app.py"])
    assert captured["cmd"][-1] == "app.py"


@pytest.mark.skipif(shutil.which("semgrep") is None, reason="semgrep not installed")
def test_real_semgrep_finds_injection(fixture_repo):
    findings = semgrep_scan.scan(fixture_repo)
    assert any("eval" in f.message.lower() or "eval" in f.file for f in findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_semgrep_scan.py -v`
Expected: FAIL — `cannot import name 'semgrep_scan'`

- [ ] **Step 3: Write semgrep_scan.py**

```python
import json
from pathlib import Path

from app.scanners.base import RawFinding, ScannerUnavailable, normalize_severity, run_tool

TOOL = "semgrep"


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    targets = files if files else ["."]
    cmd = ["semgrep", "scan", "--config", "auto", "--json", "--quiet",
           "--no-git-ignore", "--metrics", "off", *targets]
    result = run_tool(cmd, cwd=workspace)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        # Semgrep failed hard (bad config, network, crash). No findings, not a fatal error.
        return []

    findings = []
    for item in payload.get("results", []):
        extra = item.get("extra", {})
        findings.append(
            RawFinding(
                tool=TOOL,
                severity=normalize_severity(extra.get("severity", "")),
                file=item.get("path", ""),
                line=item.get("start", {}).get("line", 0),
                message=extra.get("message", item.get("check_id", "Semgrep finding")),
                category="security",
            )
        )
    return findings
```

`ScannerUnavailable` is imported so `pipeline.py` sees a consistent module surface; `run_tool` raises it and `scan` deliberately lets it propagate.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_semgrep_scan.py -v`
Expected: PASS (4 tests; the last one runs since semgrep is a pip dependency)

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: semgrep scanner"
```

---

### Task 7: Gitleaks scanner

**Files:**
- Create: `backend/app/scanners/gitleaks_scan.py`
- Test: `backend/tests/test_gitleaks_scan.py`

**Interfaces:**
- Consumes: `app.scanners.base.RawFinding`, `run_tool`
- Produces: `app.scanners.gitleaks_scan.scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]`

Gitleaks is a Go binary, not a pip package. Install it before running the integration test: `brew install gitleaks` (macOS) or grab a release from https://github.com/gitleaks/gitleaks/releases. The unit tests below run without it.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_gitleaks_scan.py`:

```python
import json
import shutil

import pytest

from app.scanners import gitleaks_scan

SAMPLE_REPORT = [
    {
        "RuleID": "aws-access-token",
        "Description": "AWS Access Key",
        "File": "config.py",
        "StartLine": 1,
        "Secret": "AKIAIOSFODNN7EXAMPLE",
    }
]


def test_parses_report_into_high_severity_findings(tmp_path, monkeypatch):
    def fake_run(cmd, cwd, timeout=600):
        report_path = cmd[cmd.index("--report-path") + 1]
        with open(report_path, "w") as handle:
            json.dump(SAMPLE_REPORT, handle)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(gitleaks_scan, "run_tool", fake_run)
    findings = gitleaks_scan.scan(tmp_path)
    assert len(findings) == 1
    assert findings[0].tool == "gitleaks"
    assert findings[0].severity == "high"
    assert findings[0].category == "security"
    assert findings[0].file == "config.py"
    assert findings[0].line == 1
    assert "AWS Access Key" in findings[0].message
    assert "AKIAIOSFODNN7EXAMPLE" not in findings[0].message  # never echo the secret


def test_missing_report_yields_no_findings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gitleaks_scan, "run_tool",
        lambda cmd, cwd, timeout=600: type(
            "R", (), {"returncode": 1, "stdout": "", "stderr": "boom"}
        )(),
    )
    assert gitleaks_scan.scan(tmp_path) == []


def test_diff_mode_filters_to_changed_files(tmp_path, monkeypatch):
    def fake_run(cmd, cwd, timeout=600):
        report_path = cmd[cmd.index("--report-path") + 1]
        with open(report_path, "w") as handle:
            json.dump(
                SAMPLE_REPORT + [{"RuleID": "x", "Description": "Other",
                                  "File": "untouched.py", "StartLine": 2}],
                handle,
            )
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(gitleaks_scan, "run_tool", fake_run)
    findings = gitleaks_scan.scan(tmp_path, files=["config.py"])
    assert [f.file for f in findings] == ["config.py"]


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks not installed")
def test_real_gitleaks_finds_planted_secret(fixture_repo):
    findings = gitleaks_scan.scan(fixture_repo)
    assert any(f.file.endswith("config.py") for f in findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_gitleaks_scan.py -v`
Expected: FAIL — `cannot import name 'gitleaks_scan'`

- [ ] **Step 3: Write gitleaks_scan.py**

```python
import json
import tempfile
from pathlib import Path

from app.scanners.base import RawFinding, ScannerUnavailable, run_tool

TOOL = "gitleaks"


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    with tempfile.TemporaryDirectory() as report_dir:
        report_path = Path(report_dir) / "gitleaks.json"
        cmd = ["gitleaks", "detect", "--no-git", "--source", ".",
               "--report-format", "json", "--report-path", str(report_path),
               "--exit-code", "0", "--redact"]
        run_tool(cmd, cwd=workspace)
        if not report_path.exists():
            return []
        try:
            report = json.loads(report_path.read_text() or "[]")
        except json.JSONDecodeError:
            return []

    changed = set(files) if files else None
    findings = []
    for leak in report or []:
        path = leak.get("File", "")
        if changed is not None and path not in changed:
            continue
        findings.append(
            RawFinding(
                tool=TOOL,
                severity="high",  # A committed credential is never "low".
                file=path,
                line=leak.get("StartLine", 0),
                message=f"{leak.get('Description', 'Secret detected')} "
                        f"(rule: {leak.get('RuleID', 'unknown')})",
                category="security",
            )
        )
    return findings
```

`--redact` keeps the secret value out of the report, so it never reaches the database or the OpenAI prompt.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_gitleaks_scan.py -v`
Expected: PASS (3 tests pass; the real-gitleaks test passes if installed, otherwise skips)

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: gitleaks secret scanner"
```

---

### Task 8: Dependency-Check scanner with license flags

**Files:**
- Create: `backend/app/scanners/depcheck_scan.py`
- Test: `backend/tests/test_depcheck_scan.py`

**Interfaces:**
- Consumes: `app.scanners.base.RawFinding`, `run_tool`, `normalize_severity`
- Produces:
  - `app.scanners.depcheck_scan.scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]`
  - `app.scanners.depcheck_scan.is_copyleft(license_text: str) -> str | None` — returns the matched license id (`"AGPL"`/`"GPL"`) or `None`

OWASP Dependency-Check needs Java 11+ and downloads the NVD database on first run (slow; an `NVD_API_KEY` env var speeds it up a lot). Install it from https://github.com/jeremylong/DependencyCheck/releases and put `dependency-check.sh` on `PATH`. The unit tests below run without it.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_depcheck_scan.py`:

```python
import json
import shutil

import pytest

from app.scanners import depcheck_scan

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


def test_missing_report_yields_no_findings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        depcheck_scan, "run_tool",
        lambda cmd, cwd, timeout=600: type(
            "R", (), {"returncode": 1, "stdout": "", "stderr": "no java"}
        )(),
    )
    assert depcheck_scan.scan(tmp_path) == []


@pytest.mark.skipif(
    shutil.which("dependency-check.sh") is None, reason="dependency-check not installed"
)
def test_real_depcheck_flags_vulnerable_flask(fixture_repo):
    findings = depcheck_scan.scan(fixture_repo)
    assert any("flask" in f.message.lower() for f in findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_depcheck_scan.py -v`
Expected: FAIL — `cannot import name 'depcheck_scan'`

- [ ] **Step 3: Write depcheck_scan.py**

```python
import json
import re
import tempfile
from pathlib import Path

from app.scanners.base import RawFinding, ScannerUnavailable, normalize_severity, run_tool

TOOL = "dependency-check"
# \bGPL deliberately does not match LGPL — a word boundary needs a non-word char before it.
_COPYLEFT = [("AGPL", re.compile(r"AGPL", re.I)), ("GPL", re.compile(r"\bGPL", re.I))]


def is_copyleft(license_text: str) -> str | None:
    """Return the copyleft family (AGPL/GPL) this license belongs to, if any."""
    for name, pattern in _COPYLEFT:
        if pattern.search(license_text or ""):
            return name
    return None


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    # Dependency-Check reads manifests, not individual source files, so diff mode
    # scans the whole tree — a changed lockfile affects every dependency.
    with tempfile.TemporaryDirectory() as out_dir:
        cmd = ["dependency-check.sh", "--scan", ".", "--format", "JSON",
               "--out", out_dir, "--project", "vibeguard", "--noupdate"]
        run_tool(cmd, cwd=workspace)
        report_path = Path(out_dir) / "dependency-check-report.json"
        if not report_path.exists():
            return []
        try:
            report = json.loads(report_path.read_text())
        except json.JSONDecodeError:
            return []

    findings = []
    for dependency in report.get("dependencies", []):
        name = dependency.get("fileName", "unknown dependency")
        manifest = Path(dependency.get("filePath", "")).name

        for vuln in dependency.get("vulnerabilities", []):
            findings.append(
                RawFinding(
                    tool=TOOL,
                    severity=normalize_severity(vuln.get("severity", "")),
                    file=manifest,
                    line=0,
                    message=f"{name}: {vuln.get('name', 'vulnerability')} — "
                            f"{vuln.get('description', '')[:300]}",
                    category="security",
                )
            )

        family = is_copyleft(dependency.get("license", ""))
        if family:
            findings.append(
                RawFinding(
                    tool=TOOL,
                    severity="medium",
                    file=manifest,
                    line=0,
                    message=f"{name} is licensed {dependency.get('license')}, a copyleft "
                            f"license that can require you to publish your source.",
                    category="license",
                    license_id=family,
                )
            )
    return findings
```

`--noupdate` keeps scans fast by reusing the cached NVD data. Run `dependency-check.sh --updateonly` once during setup to populate it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_depcheck_scan.py -v`
Expected: PASS (8 tests including parametrized cases; the real-tool test skips unless installed)

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: dependency-check scanner with copyleft license flags"
```

---

### Task 9: Vibe Debt scanner (complexity, long functions, duplicates)

**Files:**
- Create: `backend/app/scanners/lizard_scan.py`
- Test: `backend/tests/test_lizard_scan.py`

**Interfaces:**
- Consumes: `app.scanners.base.RawFinding`
- Produces: `app.scanners.lizard_scan.scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]` — all findings have `category="vibe-debt"`

Thresholds: cyclomatic complexity > 10, function length > 60 lines, duplicate normalized bodies of >= 5 lines appearing 2+ times.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_lizard_scan.py`:

```python
from app.scanners import lizard_scan


def test_flags_duplicate_function_bodies(fixture_repo):
    findings = lizard_scan.scan(fixture_repo)
    duplicates = [f for f in findings if "duplicate" in f.message.lower()]
    assert duplicates, "expected the two identical summarize_* bodies to be flagged"
    assert all(f.category == "vibe-debt" for f in duplicates)


def test_flags_high_complexity_function(fixture_repo):
    findings = lizard_scan.scan(fixture_repo)
    complex_findings = [f for f in findings if "complexity" in f.message.lower()]
    assert any("classify" in f.message for f in complex_findings)
    assert all(f.category == "vibe-debt" for f in complex_findings)


def test_all_findings_are_vibe_debt(fixture_repo):
    findings = lizard_scan.scan(fixture_repo)
    assert findings
    assert {f.category for f in findings} == {"vibe-debt"}
    assert {f.tool for f in findings} == {"lizard"}


def test_clean_code_produces_no_findings(tmp_path):
    (tmp_path / "clean.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
    )
    assert lizard_scan.scan(tmp_path) == []


def test_diff_mode_scans_only_changed_files(tmp_path):
    (tmp_path / "messy.py").write_text(
        "def f(a):\n" + "".join(
            f"    if a == {i}:\n        return {i}\n" for i in range(15)
        ) + "    return None\n"
    )
    (tmp_path / "ignored.py").write_text(
        "def g(a):\n" + "".join(
            f"    if a == {i}:\n        return {i}\n" for i in range(15)
        ) + "    return None\n"
    )
    findings = lizard_scan.scan(tmp_path, files=["messy.py"])
    assert findings
    assert {f.file for f in findings} == {"messy.py"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lizard_scan.py -v`
Expected: FAIL — `cannot import name 'lizard_scan'`

- [ ] **Step 3: Write lizard_scan.py**

```python
import hashlib
from collections import defaultdict
from pathlib import Path

import lizard

from app.scanners.base import RawFinding

TOOL = "lizard"
MAX_COMPLEXITY = 10
MAX_LENGTH = 60
MIN_DUPLICATE_LINES = 5
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}


def _candidate_files(workspace: Path, files: list[str] | None) -> list[Path]:
    if files:
        return [workspace / name for name in files if (workspace / name).is_file()]
    return [
        path for path in workspace.rglob("*")
        if path.is_file() and not SKIP_DIRS & set(path.relative_to(workspace).parts)
    ]


def _body_fingerprint(path: Path, start: int, end: int) -> str | None:
    """Hash a function body with whitespace normalized, so near-copies collide."""
    try:
        lines = path.read_text(errors="ignore").splitlines()[start - 1 : end]
    except OSError:
        return None
    normalized = [line.strip() for line in lines if line.strip()]
    if len(normalized) < MIN_DUPLICATE_LINES:
        return None
    return hashlib.sha256("\n".join(normalized).encode()).hexdigest()


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    findings: list[RawFinding] = []
    by_fingerprint: dict[str, list[tuple[str, int, str]]] = defaultdict(list)

    for path in _candidate_files(workspace, files):
        try:
            analysis = lizard.analyze_file(str(path))
        except Exception:
            continue  # lizard has no parser for this file type; nothing to say about it.
        relative = str(path.relative_to(workspace))

        for func in analysis.function_list:
            if func.cyclomatic_complexity > MAX_COMPLEXITY:
                findings.append(RawFinding(
                    tool=TOOL, severity="medium", category="vibe-debt",
                    file=relative, line=func.start_line,
                    message=f"Function '{func.name}' has cyclomatic complexity "
                            f"{func.cyclomatic_complexity} (threshold {MAX_COMPLEXITY}). "
                            f"Hard to test and easy to break on the next edit.",
                ))
            if func.length > MAX_LENGTH:
                findings.append(RawFinding(
                    tool=TOOL, severity="low", category="vibe-debt",
                    file=relative, line=func.start_line,
                    message=f"Function '{func.name}' is {func.length} lines long "
                            f"(threshold {MAX_LENGTH}). Likely doing several jobs at once.",
                ))

            fingerprint = _body_fingerprint(path, func.start_line, func.end_line)
            if fingerprint:
                by_fingerprint[fingerprint].append((relative, func.start_line, func.name))

    for locations in by_fingerprint.values():
        if len(locations) < 2:
            continue
        names = ", ".join(f"{name} ({file}:{line})" for file, line, name in locations)
        first_file, first_line, _ = locations[0]
        findings.append(RawFinding(
            tool=TOOL, severity="low", category="vibe-debt",
            file=first_file, line=first_line,
            message=f"Duplicate logic: identical function bodies in {names}. "
                    f"Fixing a bug in one leaves the copies broken.",
        ))

    return findings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lizard_scan.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: vibe debt scanner for complexity, long functions, and duplicates"
```

---

### Task 10: Scoring

**Files:**
- Create: `backend/app/scoring.py`
- Test: `backend/tests/test_scoring.py`

**Interfaces:**
- Consumes: `app.scanners.base.RawFinding`
- Produces:
  - `app.scoring.security_score(findings: list[RawFinding]) -> int` — 0–100
  - `app.scoring.vibe_debt_score(findings: list[RawFinding]) -> int` — 0–100
  - `app.scoring.SEVERITY_ORDER: list[str]` — ascending: `["info", "low", "medium", "high", "critical"]`
  - `app.scoring.meets_threshold(findings, fail_on: str) -> bool` — False when any finding is at or above `fail_on`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_scoring.py`:

```python
from app.scanners.base import RawFinding
from app.scoring import (SEVERITY_ORDER, meets_threshold, security_score,
                         vibe_debt_score)


def make(severity="high", category="security"):
    return RawFinding(tool="t", severity=severity, file="f.py", line=1,
                      message="m", category=category)


def test_clean_repo_scores_100():
    assert security_score([]) == 100
    assert vibe_debt_score([]) == 100


def test_security_score_drops_with_severity():
    assert security_score([make("critical")]) == 75
    assert security_score([make("high")]) == 85
    assert security_score([make("medium")]) == 93
    assert security_score([make("low")]) == 97
    assert security_score([make("info")]) == 99


def test_security_score_floors_at_zero():
    assert security_score([make("critical")] * 20) == 0


def test_license_findings_count_toward_security_score():
    assert security_score([make("medium", category="license")]) == 93


def test_vibe_debt_findings_do_not_touch_security_score():
    assert security_score([make("medium", category="vibe-debt")]) == 100


def test_vibe_debt_score_counts_only_vibe_debt():
    findings = [make("medium", category="vibe-debt")] * 3 + [make("high")]
    assert vibe_debt_score(findings) == 88
    assert vibe_debt_score([make("high")]) == 100


def test_severity_order_is_ascending():
    assert SEVERITY_ORDER == ["info", "low", "medium", "high", "critical"]


def test_meets_threshold():
    assert meets_threshold([make("medium")], "high")
    assert not meets_threshold([make("high")], "high")
    assert not meets_threshold([make("critical")], "high")
    assert meets_threshold([], "info")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.scoring'`

- [ ] **Step 3: Write scoring.py**

```python
from app.scanners.base import RawFinding

SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]

_PENALTY = {"critical": 25, "high": 15, "medium": 7, "low": 3, "info": 1}
_SECURITY_CATEGORIES = {"security", "license"}
# ponytail: flat 4 points per finding. Normalize by lines-of-code if big repos
# start bottoming out the score unfairly.
_VIBE_DEBT_PENALTY = 4


def security_score(findings: list[RawFinding]) -> int:
    penalty = sum(
        _PENALTY.get(f.severity, 1)
        for f in findings
        if f.category in _SECURITY_CATEGORIES
    )
    return max(0, 100 - penalty)


def vibe_debt_score(findings: list[RawFinding]) -> int:
    count = sum(1 for f in findings if f.category == "vibe-debt")
    return max(0, 100 - _VIBE_DEBT_PENALTY * count)


def meets_threshold(findings: list[RawFinding], fail_on: str) -> bool:
    """False when any finding is at or above the fail_on severity."""
    cutoff = SEVERITY_ORDER.index(fail_on)
    return not any(
        SEVERITY_ORDER.index(f.severity) >= cutoff
        for f in findings
        if f.severity in SEVERITY_ORDER
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_scoring.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: security and vibe debt scoring"
```

---

### Task 11: OpenAI reasoning layer

**Files:**
- Create: `backend/app/reasoning.py`
- Test: `backend/tests/test_reasoning.py`

**Interfaces:**
- Consumes: `app.scanners.base.RawFinding`, `app.config.settings`
- Produces: `app.reasoning.annotate(findings: list[RawFinding]) -> list[dict] | None` — returns a list the same length as `findings`, each `{"explanation": str, "fix": str}`; returns `None` when the AI layer is unavailable (no key, API error, malformed response). The caller treats `None` as "explanations unavailable" and still ships the report.

The prompt sends the findings in and asks only for prose back. It never asks the model for new findings, and any extra entries the model returns are discarded by index alignment.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_reasoning.py`:

```python
import json

from app.scanners.base import RawFinding
from app import reasoning
from app.config import settings


def make(n=2):
    return [
        RawFinding(tool="semgrep", severity="high", file=f"a{i}.py", line=i,
                   message=f"issue {i}")
        for i in range(n)
    ]


class FakeOpenAI:
    def __init__(self, payload=None, error=None):
        self._payload, self._error = payload, error
        outer = self

        class Completions:
            def create(self, **kwargs):
                outer.last_kwargs = kwargs
                if outer._error:
                    raise outer._error
                message = type("M", (), {"content": json.dumps(outer._payload)})()
                choice = type("C", (), {"message": message})()
                return type("R", (), {"choices": [choice]})()

        self.chat = type("Chat", (), {"completions": Completions()})()


def test_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert reasoning.annotate(make()) is None


def test_annotates_each_finding(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    fake = FakeOpenAI({"annotations": [
        {"index": 0, "explanation": "Attackers run code.", "fix": "Drop eval."},
        {"index": 1, "explanation": "Shell injection.", "fix": "Pass a list."},
    ]})
    monkeypatch.setattr(reasoning, "_client", lambda: fake)

    result = reasoning.annotate(make())
    assert len(result) == 2
    assert result[0]["explanation"] == "Attackers run code."
    assert result[1]["fix"] == "Pass a list."


def test_api_error_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(reasoning, "_client", lambda: FakeOpenAI(error=RuntimeError("503")))
    assert reasoning.annotate(make()) is None


def test_missing_annotations_are_filled_with_blanks(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    fake = FakeOpenAI({"annotations": [
        {"index": 1, "explanation": "Only the second.", "fix": "Fix it."}
    ]})
    monkeypatch.setattr(reasoning, "_client", lambda: fake)

    result = reasoning.annotate(make())
    assert len(result) == 2
    assert result[0] == {"explanation": "", "fix": ""}
    assert result[1]["explanation"] == "Only the second."


def test_extra_annotations_are_discarded(monkeypatch):
    """The model must not be able to invent findings we never detected."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    fake = FakeOpenAI({"annotations": [
        {"index": 0, "explanation": "Real.", "fix": "Fix."},
        {"index": 1, "explanation": "Real.", "fix": "Fix."},
        {"index": 99, "explanation": "Invented.", "fix": "Nope."},
    ]})
    monkeypatch.setattr(reasoning, "_client", lambda: fake)

    result = reasoning.annotate(make())
    assert len(result) == 2
    assert all("Invented" not in r["explanation"] for r in result)


def test_empty_findings_short_circuits(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    assert reasoning.annotate([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_reasoning.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.reasoning'`

- [ ] **Step 3: Write reasoning.py**

```python
import json

from openai import OpenAI

from app.config import settings
from app.scanners.base import RawFinding

BATCH_SIZE = 25

SYSTEM_PROMPT = (
    "You are a security reviewer helping a developer who has no security background. "
    "You will receive a JSON list of findings that deterministic scanners already "
    "produced. For each finding, explain in two or three plain sentences what an "
    "attacker or maintainer could actually do with it, then give a concrete fix. "
    "You must never add, invent, merge, or remove findings — annotate exactly the "
    "indexes you are given. Reply with JSON: "
    '{"annotations": [{"index": <int>, "explanation": "<text>", "fix": "<text>"}]}'
)


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def _payload(findings: list[RawFinding], offset: int) -> str:
    return json.dumps([
        {
            "index": offset + i,
            "tool": f.tool,
            "severity": f.severity,
            "category": f.category,
            "file": f.file,
            "line": f.line,
            "message": f.message,
        }
        for i, f in enumerate(findings)
    ])


def annotate(findings: list[RawFinding]) -> list[dict] | None:
    """Explain and suggest fixes for findings. None means the AI layer is unavailable."""
    if not findings:
        return []
    if not settings.openai_api_key:
        return None

    results: list[dict] = [{"explanation": "", "fix": ""} for _ in findings]
    try:
        client = _client()
        for offset in range(0, len(findings), BATCH_SIZE):
            batch = findings[offset : offset + BATCH_SIZE]
            response = client.chat.completions.create(
                model=settings.openai_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _payload(batch, offset)},
                ],
            )
            payload = json.loads(response.choices[0].message.content)
            for item in payload.get("annotations", []):
                index = item.get("index")
                # Out-of-range indexes are dropped: the model cannot add findings.
                if isinstance(index, int) and 0 <= index < len(results):
                    results[index] = {
                        "explanation": str(item.get("explanation", "")),
                        "fix": str(item.get("fix", "")),
                    }
    except Exception:
        # Any failure (no network, rate limit, bad JSON) degrades to "no explanations".
        return None
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_reasoning.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: OpenAI reasoning layer that annotates but never invents findings"
```

---

### Task 12: Scan pipeline orchestration

**Files:**
- Create: `backend/app/pipeline.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `app.intake.prepare`, all four scanner modules, `app.reasoning.annotate`, `app.scoring`, `app.db.SessionLocal`, `app.models.Scan/Finding`
- Produces:
  - `app.pipeline.SCANNERS: list` — the four scanner modules, in order
  - `app.pipeline.run_scan(scan_id: int) -> None` — opens its own DB session, drives the whole scan, never raises

- [ ] **Step 1: Write the failing test**

`backend/tests/test_pipeline.py`:

```python
import pytest

from app import pipeline
from app.models import Scan, User
from app.scanners.base import RawFinding, ScannerUnavailable


@pytest.fixture()
def scan_row(db, tmp_path):
    user = User(email="p@b.com", password_hash="x")
    db.add(user)
    db.flush()
    (tmp_path / "app.py").write_text("print(1)\n")
    scan = Scan(user_id=user.id, repo_key="acme/demo", mode="full",
                status="pending", source_type="git", source_ref=str(tmp_path))
    db.add(scan)
    db.commit()
    return scan


def fake_scanner(findings=None, error=None):
    def scan(workspace, files=None):
        if error:
            raise error
        return findings or []
    return type("FakeScanner", (), {"scan": staticmethod(scan)})


def test_successful_scan_persists_findings_and_scores(db, scan_row, monkeypatch):
    monkeypatch.setattr(pipeline, "SCANNERS", [
        fake_scanner([RawFinding("semgrep", "high", "app.py", 1, "eval used")]),
        fake_scanner([RawFinding("lizard", "low", "dup.py", 2, "dup", "vibe-debt")]),
    ])
    monkeypatch.setattr(pipeline, "annotate", lambda f: [
        {"explanation": "Bad.", "fix": "Remove it."} for _ in f
    ])

    pipeline.run_scan(scan_row.id)

    db.expire_all()
    scan = db.get(Scan, scan_row.id)
    assert scan.status == "done"
    assert scan.security_score == 85
    assert scan.vibe_debt_score == 96
    assert scan.ai_available is True
    assert len(scan.findings) == 2
    assert scan.findings[0].ai_explanation == "Bad."


def test_scan_completes_when_one_scanner_fails(db, scan_row, monkeypatch):
    monkeypatch.setattr(pipeline, "SCANNERS", [
        fake_scanner([RawFinding("semgrep", "high", "app.py", 1, "eval used")]),
        fake_scanner(error=ScannerUnavailable("gitleaks missing")),
    ])
    monkeypatch.setattr(pipeline, "annotate", lambda f: None)

    pipeline.run_scan(scan_row.id)

    db.expire_all()
    scan = db.get(Scan, scan_row.id)
    assert scan.status == "done"
    assert len(scan.findings) == 1
    assert "gitleaks" in (scan.error or "")


def test_scan_fails_only_when_every_scanner_fails(db, scan_row, monkeypatch):
    monkeypatch.setattr(pipeline, "SCANNERS", [
        fake_scanner(error=ScannerUnavailable("semgrep missing")),
        fake_scanner(error=ScannerUnavailable("gitleaks missing")),
    ])
    monkeypatch.setattr(pipeline, "annotate", lambda f: None)

    pipeline.run_scan(scan_row.id)

    db.expire_all()
    scan = db.get(Scan, scan_row.id)
    assert scan.status == "failed"
    assert scan.findings == []


def test_ai_failure_still_produces_a_report(db, scan_row, monkeypatch):
    monkeypatch.setattr(pipeline, "SCANNERS", [
        fake_scanner([RawFinding("semgrep", "high", "app.py", 1, "eval used")]),
    ])
    monkeypatch.setattr(pipeline, "annotate", lambda f: None)

    pipeline.run_scan(scan_row.id)

    db.expire_all()
    scan = db.get(Scan, scan_row.id)
    assert scan.status == "done"
    assert scan.ai_available is False
    assert scan.findings[0].ai_explanation is None
    assert scan.security_score == 85


def test_bad_source_marks_scan_failed(db, scan_row, monkeypatch):
    scan_row.source_ref = "https://github.com/does-not/exist-xyz.git"
    db.commit()
    monkeypatch.setattr(pipeline, "SCANNERS", [fake_scanner([])])

    pipeline.run_scan(scan_row.id)

    db.expire_all()
    scan = db.get(Scan, scan_row.id)
    assert scan.status == "failed"
    assert scan.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.pipeline'`

- [ ] **Step 3: Write pipeline.py**

```python
import logging

from app.db import SessionLocal
from app.intake import IntakeError, prepare
from app.models import Finding, Scan
from app.reasoning import annotate
from app.scanners import depcheck_scan, gitleaks_scan, lizard_scan, semgrep_scan
from app.scanners.base import RawFinding
from app.scoring import security_score, vibe_debt_score

log = logging.getLogger(__name__)

SCANNERS = [semgrep_scan, gitleaks_scan, depcheck_scan, lizard_scan]


def run_scan(scan_id: int) -> None:
    """Run one scan end to end. Never raises — failures land in scan.status."""
    session = SessionLocal()
    try:
        scan = session.get(Scan, scan_id)
        if scan is None:
            return
        scan.status = "running"
        session.commit()

        try:
            with prepare(scan.source_type, scan.source_ref,
                         scan.base_ref, scan.head_ref) as workspace:
                findings, failures = _run_scanners(workspace)
        except IntakeError as exc:
            _fail(session, scan, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - a crashed scan must not kill the worker
            log.exception("scan %s crashed during intake", scan_id)
            _fail(session, scan, f"Could not prepare the code for scanning: {exc}")
            return

        if len(failures) == len(SCANNERS):
            _fail(session, scan, "; ".join(failures) or "All scanners failed")
            return

        annotations = annotate(findings)
        scan.ai_available = annotations is not None

        for index, raw in enumerate(findings):
            note = annotations[index] if annotations else {}
            session.add(Finding(
                scan_id=scan.id, tool=raw.tool, severity=raw.severity,
                category=raw.category, file=raw.file, line=raw.line,
                message=raw.message, license_id=raw.license_id,
                ai_explanation=note.get("explanation") or None,
                ai_fix=note.get("fix") or None,
            ))

        scan.security_score = security_score(findings)
        scan.vibe_debt_score = vibe_debt_score(findings)
        scan.error = "; ".join(failures) or None
        scan.status = "done"
        session.commit()
    finally:
        session.close()


def _run_scanners(workspace) -> tuple[list[RawFinding], list[str]]:
    findings: list[RawFinding] = []
    failures: list[str] = []
    for scanner in SCANNERS:
        try:
            findings.extend(scanner.scan(workspace.path, workspace.files))
        except Exception as exc:  # noqa: BLE001 - one bad tool must not sink the scan
            log.warning("scanner %s failed: %s", scanner.__name__, exc)
            failures.append(f"{scanner.__name__.split('.')[-1]}: {exc}")
    return findings, failures


def _fail(session, scan: Scan, message: str) -> None:
    scan.status = "failed"
    scan.error = message[:500]
    session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_pipeline.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: scan pipeline orchestration with partial-failure tolerance"
```

---

### Task 13: Scan API routes

**Files:**
- Create: `backend/app/routes_scans.py`
- Modify: `backend/app/main.py` (mount the new router)
- Test: `backend/tests/test_routes_scans.py`

**Interfaces:**
- Consumes: `app.auth.current_user`, `app.db.get_db`, `app.intake.repo_key_from_url/repo_key_from_bytes/IntakeError`, `app.pipeline.run_scan`, `app.scoring.SEVERITY_ORDER/meets_threshold`
- Produces:
  - `POST /scans` (multipart form: `repo_url`, `zip_file`, `base_ref`, `head_ref`) → `201 {"id": int, "status": "pending"}`
  - `GET /scans` (optional `?repo_key=`) → list of scan summaries, newest first — powers the trend chart
  - `GET /scans/{id}` → full report with findings
  - `GET /scans/{id}/status?fail_on=high` → `{"scan_id", "status", "passed", "security_score", "vibe_debt_score"}`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_routes_scans.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_routes_scans.py -v`
Expected: FAIL — `cannot import name 'routes_scans'`

- [ ] **Step 3: Write routes_scans.py**

```python
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                     HTTPException, Query, UploadFile)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.intake import IntakeError, repo_key_from_bytes, repo_key_from_url
from app.models import Finding, Scan, User
from app.pipeline import run_scan
from app.scanners.base import RawFinding
from app.scoring import SEVERITY_ORDER, meets_threshold

router = APIRouter(prefix="/scans", tags=["scans"])


class ScanCreated(BaseModel):
    id: int
    status: str


class ScanSummary(BaseModel):
    id: int
    repo_key: str
    mode: str
    status: str
    security_score: int | None
    vibe_debt_score: int | None
    created_at: datetime


class FindingOut(BaseModel):
    id: int
    tool: str
    severity: str
    category: str
    file: str
    line: int
    message: str
    license_id: str | None
    ai_explanation: str | None
    ai_fix: str | None


class ScanReport(ScanSummary):
    ai_available: bool
    error: str | None
    findings: list[FindingOut]


def _owned_scan(scan_id: int, user: User, db: Session) -> Scan:
    scan = db.get(Scan, scan_id)
    if scan is None or scan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


@router.post("", status_code=201, response_model=ScanCreated)
def create_scan(
    background: BackgroundTasks,
    repo_url: str | None = Form(None),
    zip_file: UploadFile | None = File(None),
    base_ref: str | None = Form(None),
    head_ref: str | None = Form(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if repo_url:
        try:
            repo_key = repo_key_from_url(repo_url)
        except IntakeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        source_type, source_ref = "git", repo_url
    elif zip_file is not None:
        data = zip_file.file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        repo_key = repo_key_from_bytes(data)
        # The pipeline reads this back, then intake deletes its own workspace.
        handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        handle.write(data)
        handle.close()
        source_type, source_ref = "zip", handle.name
    else:
        raise HTTPException(status_code=400, detail="Provide a repo_url or a zip_file")

    scan = Scan(
        user_id=user.id, repo_key=repo_key, status="pending",
        mode="diff" if (base_ref and head_ref) else "full",
        source_type=source_type, source_ref=source_ref,
        base_ref=base_ref, head_ref=head_ref,
    )
    db.add(scan)
    db.commit()

    background.add_task(run_scan, scan.id)
    return ScanCreated(id=scan.id, status=scan.status)


@router.get("", response_model=list[ScanSummary])
def list_scans(
    repo_key: str | None = Query(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Scan).filter(Scan.user_id == user.id)
    if repo_key:
        query = query.filter(Scan.repo_key == repo_key)
    return query.order_by(Scan.id.desc()).limit(50).all()


@router.get("/{scan_id}", response_model=ScanReport)
def get_scan(scan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    scan = _owned_scan(scan_id, user, db)
    order = {name: i for i, name in enumerate(reversed(SEVERITY_ORDER))}
    scan.findings.sort(key=lambda f: order.get(f.severity, 99))
    return scan


@router.get("/{scan_id}/status")
def scan_status(
    scan_id: int,
    fail_on: str = Query("high"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if fail_on not in SEVERITY_ORDER:
        raise HTTPException(
            status_code=422, detail=f"fail_on must be one of {SEVERITY_ORDER}"
        )
    scan = _owned_scan(scan_id, user, db)
    raw = [
        RawFinding(tool=f.tool, severity=f.severity, file=f.file, line=f.line,
                   message=f.message, category=f.category)
        for f in scan.findings
    ]
    return {
        "scan_id": scan.id,
        "status": scan.status,
        "passed": scan.status == "done" and meets_threshold(raw, fail_on),
        "security_score": scan.security_score,
        "vibe_debt_score": scan.vibe_debt_score,
    }
```

Add `from pydantic import ConfigDict` usage by giving `ScanSummary`, `FindingOut`, and `ScanReport` ORM mode — add this line to each of those three classes:

```python
    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Mount the router in main.py**

Change the import line and add one `include_router` call:

```python
from app import routes_auth, routes_scans
```

```python
app.include_router(routes_auth.router)
app.include_router(routes_scans.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_routes_scans.py -v`
Expected: PASS (11 tests)

- [ ] **Step 6: Run the whole backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: scan API with diff mode, trend listing, and CI status gate"
```

---

### Task 14: End-to-end pipeline test (the spec's required check)

**Files:**
- Test: `backend/tests/test_scan_pipeline.py`
- Create: `backend/README.md`

**Interfaces:**
- Consumes: everything built so far
- Produces: no new code — this is the one check that fails if the scan pipeline breaks

- [ ] **Step 1: Write the end-to-end test**

`backend/tests/test_scan_pipeline.py`:

```python
"""End-to-end check from the spec: a repo with a planted secret, a vulnerable
dependency, and duplicated code must produce all three finding kinds."""

import shutil

import pytest

from app import pipeline
from app.models import Scan, User


@pytest.fixture()
def scan_of_fixture(db, fixture_repo, tmp_path):
    workspace = tmp_path / "repo"
    shutil.copytree(fixture_repo, workspace)
    user = User(email="e2e@b.com", password_hash="x")
    db.add(user)
    db.flush()
    scan = Scan(user_id=user.id, repo_key="acme/vulnerable", mode="full",
                status="pending", source_type="git", source_ref=str(workspace))
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

    if shutil.which("gitleaks"):
        assert any(f.tool == "gitleaks" for f in scan.findings), "planted secret missed"
    if shutil.which("dependency-check.sh"):
        assert any("flask" in f.message.lower() for f in scan.findings), \
            "vulnerable flask dependency missed"

    assert scan.security_score is not None
    assert scan.vibe_debt_score is not None
    assert scan.vibe_debt_score < 100, "duplicated code should cost vibe debt points"
    assert scan.ai_available is False
```

- [ ] **Step 2: Run it**

Run: `cd backend && python -m pytest tests/test_scan_pipeline.py -v`
Expected: PASS. Semgrep and lizard run from pip; the gitleaks and dependency-check assertions activate only when those binaries are installed.

- [ ] **Step 3: Write the backend README**

`backend/README.md`:

```markdown
# VibeGuard Backend

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in OPENAI_API_KEY and the GitHub OAuth pair
```

Postgres:

```bash
createdb vibeguard
```

Scanner binaries that are not pip packages:

- **Gitleaks** — `brew install gitleaks`, or a release from
  https://github.com/gitleaks/gitleaks/releases
- **OWASP Dependency-Check** — needs Java 11+. Download from
  https://github.com/jeremylong/DependencyCheck/releases, put
  `dependency-check.sh` on your PATH, then populate the CVE cache once:
  `dependency-check.sh --updateonly` (set `NVD_API_KEY` first; it is much
  faster with one).

Semgrep and lizard install from `requirements.txt`.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
python -m pytest -v
```

Scanner tests that need a missing binary skip themselves rather than fail.

## Using the status endpoint as a CI gate

```bash
curl -s "http://localhost:8000/scans/$SCAN_ID/status?fail_on=high" | jq -e '.passed'
```
```

- [ ] **Step 4: Commit**

```bash
git add backend/
git commit -m "test: end-to-end scan pipeline check and backend setup docs"
```

---

### Task 15: Frontend scaffold, API client, auth pages

**Files:**
- Create: `frontend/` (via `create-next-app`)
- Create: `frontend/lib/api.ts`
- Create: `frontend/app/login/page.tsx`
- Create: `frontend/app/signup/page.tsx`
- Modify: `frontend/app/layout.tsx`
- Create: `frontend/.env.local.example`

**Interfaces:**
- Consumes: the backend auth API from Tasks 2 and 3
- Produces:
  - `lib/api.ts` exports: `api<T>(path: string, init?: RequestInit): Promise<T>`, `ApiError`, types `User`, `ScanSummary`, `Finding`, `ScanReport`, and helpers `signup`, `login`, `logout`, `me`, `createScan`, `listScans`, `getScan`

- [ ] **Step 1: Scaffold the app**

From the repository root:

```bash
npx create-next-app@latest frontend --typescript --tailwind --app --eslint --no-src-dir --import-alias "@/*" --use-npm
```

Create `frontend/.env.local.example`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Copy it: `cp frontend/.env.local.example frontend/.env.local`

- [ ] **Step 2: Write lib/api.ts**

```typescript
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { credentials: "include", ...init });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new ApiError(res.status, detail.detail ?? res.statusText);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export type User = { id: number; email: string };

export type ScanSummary = {
  id: number;
  repo_key: string;
  mode: "full" | "diff";
  status: "pending" | "running" | "done" | "failed";
  security_score: number | null;
  vibe_debt_score: number | null;
  created_at: string;
};

export type Finding = {
  id: number;
  tool: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  category: "security" | "vibe-debt" | "license";
  file: string;
  line: number;
  message: string;
  license_id: string | null;
  ai_explanation: string | null;
  ai_fix: string | null;
};

export type ScanReport = ScanSummary & {
  ai_available: boolean;
  error: string | null;
  findings: Finding[];
};

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const signup = (email: string, password: string) =>
  api<User>("/auth/signup", json({ email, password }));
export const login = (email: string, password: string) =>
  api<User>("/auth/login", json({ email, password }));
export const logout = () => api<void>("/auth/logout", { method: "POST" });
export const me = () => api<User>("/auth/me");
export const githubLoginUrl = () => `${BASE}/auth/github/login`;

export const createScan = (form: FormData) =>
  api<{ id: number; status: string }>("/scans", { method: "POST", body: form });
export const listScans = (repoKey?: string) =>
  api<ScanSummary[]>(`/scans${repoKey ? `?repo_key=${encodeURIComponent(repoKey)}` : ""}`);
export const getScan = (id: number) => api<ScanReport>(`/scans/${id}`);
```

- [ ] **Step 3: Write the login page**

`frontend/app/login/page.tsx`:

```tsx
"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { githubLoginUrl, login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <h1 className="text-2xl font-semibold">Sign in to VibeGuard</h1>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <input
          type="email" required placeholder="you@example.com" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded border border-gray-300 px-3 py-2"
        />
        <input
          type="password" required placeholder="Password" value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded border border-gray-300 px-3 py-2"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit" disabled={busy}
          className="rounded bg-black px-3 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <a href={githubLoginUrl()} className="rounded border px-3 py-2 text-center">
        Continue with GitHub
      </a>
      <p className="text-sm text-gray-600">
        No account? <Link href="/signup" className="underline">Sign up</Link>
      </p>
    </main>
  );
}
```

- [ ] **Step 4: Write the signup page**

`frontend/app/signup/page.tsx` — same shape, calling `signup` instead:

```tsx
"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { githubLoginUrl, signup } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signup(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <h1 className="text-2xl font-semibold">Create a VibeGuard account</h1>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <input
          type="email" required placeholder="you@example.com" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded border border-gray-300 px-3 py-2"
        />
        <input
          type="password" required minLength={8} placeholder="Password (8+ characters)"
          value={password} onChange={(e) => setPassword(e.target.value)}
          className="rounded border border-gray-300 px-3 py-2"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit" disabled={busy}
          className="rounded bg-black px-3 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
      <a href={githubLoginUrl()} className="rounded border px-3 py-2 text-center">
        Continue with GitHub
      </a>
      <p className="text-sm text-gray-600">
        Already registered? <Link href="/login" className="underline">Sign in</Link>
      </p>
    </main>
  );
}
```

- [ ] **Step 5: Verify manually**

Run the backend (`uvicorn app.main:app --reload --port 8000`) and `npm run dev` in `frontend/`.
Visit http://localhost:3000/signup, create an account, confirm you land on `/` without an error.

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: frontend scaffold, typed API client, and auth pages"
```

---

### Task 16: Dashboard — submit a scan, list past scans

**Files:**
- Create: `frontend/components/ScoreBadge.tsx`
- Modify: `frontend/app/page.tsx` (replace the create-next-app default)

**Interfaces:**
- Consumes: `lib/api.ts` (`me`, `logout`, `createScan`, `listScans`), types `ScanSummary`
- Produces: `components/ScoreBadge.tsx` default export — `ScoreBadge({ label, score }: { label: string; score: number | null })`

- [ ] **Step 1: Write ScoreBadge.tsx**

```tsx
export default function ScoreBadge({
  label,
  score,
}: {
  label: string;
  score: number | null;
}) {
  const tone =
    score === null ? "bg-gray-100 text-gray-500"
    : score >= 80 ? "bg-green-100 text-green-800"
    : score >= 50 ? "bg-amber-100 text-amber-800"
    : "bg-red-100 text-red-800";

  return (
    <span className={`inline-flex items-baseline gap-1 rounded px-2 py-1 text-sm ${tone}`}>
      <span className="font-medium">{label}</span>
      <span className="tabular-nums">{score ?? "—"}</span>
    </span>
  );
}
```

- [ ] **Step 2: Write the dashboard page**

`frontend/app/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ScoreBadge from "@/components/ScoreBadge";
import { createScan, listScans, logout, me, type ScanSummary } from "@/lib/api";

export default function Dashboard() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [scans, setScans] = useState<ScanSummary[]>([]);
  const [repoUrl, setRepoUrl] = useState("");
  const [zip, setZip] = useState<File | null>(null);
  const [baseRef, setBaseRef] = useState("");
  const [headRef, setHeadRef] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setScans(await listScans());
  }, []);

  useEffect(() => {
    me()
      .then((user) => setEmail(user.email))
      .then(refresh)
      .catch(() => router.push("/login"));
  }, [refresh, router]);

  // Past scans include pending/running ones; poll while any are unfinished.
  useEffect(() => {
    if (!scans.some((s) => s.status === "pending" || s.status === "running")) return;
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [scans, refresh]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData();
    if (repoUrl) form.append("repo_url", repoUrl);
    if (zip) form.append("zip_file", zip);
    if (baseRef && headRef) {
      form.append("base_ref", baseRef);
      form.append("head_ref", headRef);
    }
    try {
      const created = await createScan(form);
      router.push(`/scans/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the scan");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-6">
      <header className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">VibeGuard</h1>
        <div className="flex items-center gap-3 text-sm text-gray-600">
          <span>{email}</span>
          <button
            onClick={() => logout().then(() => router.push("/login"))}
            className="underline"
          >
            Sign out
          </button>
        </div>
      </header>

      <form onSubmit={submit} className="mb-10 flex flex-col gap-3 rounded border p-4">
        <h2 className="font-medium">Scan a repository</h2>
        <input
          type="url" placeholder="https://github.com/owner/repo" value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          className="rounded border border-gray-300 px-3 py-2"
        />
        <div className="text-center text-sm text-gray-500">or upload a zip</div>
        <input
          type="file" accept=".zip"
          onChange={(e) => setZip(e.target.files?.[0] ?? null)}
          className="text-sm"
        />
        <details className="text-sm">
          <summary className="cursor-pointer text-gray-600">
            Scan only a diff (optional)
          </summary>
          <div className="mt-2 flex gap-2">
            <input
              placeholder="base ref (e.g. main)" value={baseRef}
              onChange={(e) => setBaseRef(e.target.value)}
              className="flex-1 rounded border border-gray-300 px-3 py-2"
            />
            <input
              placeholder="head ref (e.g. my-branch)" value={headRef}
              onChange={(e) => setHeadRef(e.target.value)}
              className="flex-1 rounded border border-gray-300 px-3 py-2"
            />
          </div>
        </details>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit" disabled={busy || (!repoUrl && !zip)}
          className="self-start rounded bg-black px-4 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Starting…" : "Start scan"}
        </button>
      </form>

      <h2 className="mb-3 font-medium">Past scans</h2>
      {scans.length === 0 ? (
        <p className="text-sm text-gray-500">Nothing scanned yet.</p>
      ) : (
        <ul className="divide-y rounded border">
          {scans.map((scan) => (
            <li key={scan.id}>
              <Link
                href={`/scans/${scan.id}`}
                className="flex items-center justify-between gap-3 p-3 hover:bg-gray-50"
              >
                <div>
                  <div className="font-medium">{scan.repo_key}</div>
                  <div className="text-xs text-gray-500">
                    {scan.status}
                    {scan.mode === "diff" && " · diff"} ·{" "}
                    {new Date(scan.created_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex gap-2">
                  <ScoreBadge label="Security" score={scan.security_score} />
                  <ScoreBadge label="Vibe Debt" score={scan.vibe_debt_score} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 3: Verify manually**

With both servers running, sign in and submit `https://github.com/owner/repo`.
Expected: you land on the scan page, and returning to `/` lists the scan with a live-updating status.

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: dashboard with scan submission and history"
```

---

### Task 17: Report view with findings and score trend

**Files:**
- Create: `frontend/components/Sparkline.tsx`
- Create: `frontend/components/FindingCard.tsx`
- Create: `frontend/app/scans/[id]/page.tsx`

**Interfaces:**
- Consumes: `lib/api.ts` (`getScan`, `listScans`), `components/ScoreBadge`, types `ScanReport`, `Finding`, `ScanSummary`
- Produces:
  - `components/Sparkline.tsx` default export — `Sparkline({ points }: { points: number[] })`, inline SVG, no chart library
  - `components/FindingCard.tsx` default export — `FindingCard({ finding }: { finding: Finding })`

- [ ] **Step 1: Write Sparkline.tsx**

```tsx
export default function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null;

  const width = 160;
  const height = 40;
  const step = width / (points.length - 1);
  const path = points
    .map((value, i) => `${i === 0 ? "M" : "L"} ${i * step} ${height - (value / 100) * height}`)
    .join(" ");

  return (
    <svg width={width} height={height} className="overflow-visible">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="2" />
      <circle
        cx={width}
        cy={height - (points[points.length - 1] / 100) * height}
        r="3"
        fill="currentColor"
      />
    </svg>
  );
}
```

- [ ] **Step 2: Write FindingCard.tsx**

```tsx
import type { Finding } from "@/lib/api";

const SEVERITY_TONE: Record<Finding["severity"], string> = {
  critical: "border-red-500 bg-red-50",
  high: "border-orange-500 bg-orange-50",
  medium: "border-amber-500 bg-amber-50",
  low: "border-sky-500 bg-sky-50",
  info: "border-gray-300 bg-gray-50",
};

export default function FindingCard({ finding }: { finding: Finding }) {
  return (
    <li className={`rounded border-l-4 p-4 ${SEVERITY_TONE[finding.severity]}`}>
      <div className="flex flex-wrap items-baseline gap-2 text-xs text-gray-600">
        <span className="font-semibold uppercase">{finding.severity}</span>
        <span>· {finding.category}</span>
        <span>· {finding.tool}</span>
        <span className="font-mono">
          {finding.file}
          {finding.line > 0 && `:${finding.line}`}
        </span>
      </div>
      <p className="mt-2 text-sm">{finding.message}</p>
      {finding.ai_explanation && (
        <p className="mt-3 text-sm">
          <span className="font-medium">Why it matters: </span>
          {finding.ai_explanation}
        </p>
      )}
      {finding.ai_fix && (
        <p className="mt-2 text-sm">
          <span className="font-medium">Suggested fix: </span>
          {finding.ai_fix}
        </p>
      )}
    </li>
  );
}
```

- [ ] **Step 3: Write the report page**

`frontend/app/scans/[id]/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import FindingCard from "@/components/FindingCard";
import ScoreBadge from "@/components/ScoreBadge";
import Sparkline from "@/components/Sparkline";
import { getScan, listScans, type ScanReport, type ScanSummary } from "@/lib/api";

export default function ScanPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const scanId = Number(id);
  const [scan, setScan] = useState<ScanReport | null>(null);
  const [history, setHistory] = useState<ScanSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function poll() {
      try {
        const report = await getScan(scanId);
        if (!active) return;
        setScan(report);
        if (report.status === "done" || report.status === "failed") {
          setHistory((await listScans(report.repo_key)).reverse());
          return;
        }
        setTimeout(poll, 3000);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Could not load the scan");
      }
    }

    poll();
    return () => {
      active = false;
    };
  }, [scanId, router]);

  if (error) return <main className="p-6 text-red-600">{error}</main>;
  if (!scan) return <main className="p-6 text-gray-500">Loading…</main>;

  const trend = history
    .filter((s) => s.security_score !== null)
    .map((s) => s.security_score as number);

  return (
    <main className="mx-auto max-w-3xl p-6">
      <Link href="/" className="text-sm underline">
        ← All scans
      </Link>

      <header className="mt-4 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{scan.repo_key}</h1>
          <p className="text-sm text-gray-500">
            {scan.status}
            {scan.mode === "diff" && " · diff only"} ·{" "}
            {new Date(scan.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex gap-2">
          <ScoreBadge label="Security" score={scan.security_score} />
          <ScoreBadge label="Vibe Debt" score={scan.vibe_debt_score} />
        </div>
      </header>

      {(scan.status === "pending" || scan.status === "running") && (
        <p className="mt-6 rounded border bg-gray-50 p-4 text-sm">
          Scanning… this page updates itself.
        </p>
      )}

      {scan.status === "failed" && (
        <p className="mt-6 rounded border border-red-300 bg-red-50 p-4 text-sm">
          Scan failed: {scan.error ?? "unknown error"}
        </p>
      )}

      {scan.status === "done" && !scan.ai_available && (
        <p className="mt-6 rounded border border-amber-300 bg-amber-50 p-4 text-sm">
          AI explanations unavailable for this scan — findings below are raw
          scanner output.
        </p>
      )}

      {scan.status === "done" && scan.error && (
        <p className="mt-4 rounded border border-amber-300 bg-amber-50 p-4 text-sm">
          Partial scan — some tools did not run: {scan.error}
        </p>
      )}

      {trend.length > 1 && (
        <section className="mt-8">
          <h2 className="mb-2 font-medium">Security score over time</h2>
          <div className="text-gray-800">
            <Sparkline points={trend} />
          </div>
          <p className="text-xs text-gray-500">
            {trend.length} scans of {scan.repo_key}
          </p>
        </section>
      )}

      {scan.status === "done" && (
        <section className="mt-8">
          <h2 className="mb-3 font-medium">
            {scan.findings.length} finding{scan.findings.length === 1 ? "" : "s"}
          </h2>
          {scan.findings.length === 0 ? (
            <p className="text-sm text-gray-500">Nothing flagged. Clean scan.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {scan.findings.map((finding) => (
                <FindingCard key={finding.id} finding={finding} />
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}
```

- [ ] **Step 4: Verify manually end to end**

With both servers running and `OPENAI_API_KEY` set in `backend/.env`:
1. Sign in, submit a small public repo.
2. Watch the report page flip from "Scanning…" to findings without a manual refresh.
3. Confirm findings show severity, file:line, and an AI "Why it matters" paragraph.
4. Submit the same repo again and confirm the sparkline appears with two points.

- [ ] **Step 5: Run the full backend suite one more time**

Run: `cd backend && python -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: scan report view with findings, AI explanations, and score trend"
```

---

## Deferred to later specs

Not built by this plan, per the spec's scope section: Docker/QEMU sandboxed execution, fuzzing and mutation testing, the Tribal Knowledge Graph, the Integration Drift Simulator, an IDE plugin, a real job queue, and object storage.
