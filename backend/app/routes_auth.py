import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth import (COOKIE_NAME, cookie_policy, create_token, current_user,
                      hash_password, set_auth_cookie, verify_password)
from app.config import settings
from app.db import get_db
from app.models import User
from fastapi.responses import RedirectResponse

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
    # Attributes must match the ones it was set with or the browser keeps it.
    response.delete_cookie(COOKIE_NAME, path="/", **cookie_policy())


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(id=user.id, email=user.email)


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

        # Only use verified primary email from /user/emails endpoint
        emails = http.get(f"{GITHUB_API}/user/emails", headers=headers).json()
        verified_primary = next(
            (e for e in emails if e.get("primary") and e.get("verified")),
            None
        )
        email = verified_primary["email"] if verified_primary else f"{profile['id']}@users.noreply.github.com"
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
