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
