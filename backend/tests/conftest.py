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
