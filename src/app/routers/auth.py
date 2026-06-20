"""Authentication: sign in / sign up / logout / password reset."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.email_utils import send_reset_code
from app.models import PasswordReset, User
from app.security import (
    hash_password,
    make_session_token,
    new_reset_code,
    verify_password,
)
from app.templating import templates

router = APIRouter()


def _auth_page(
    request: Request,
    mode: str = "signin",
    message: str = "",
    ok_message: bool = False,
    **ctx,
):
    return templates.TemplateResponse(
        "auth.html",
        {
            "request": request,
            "mode": mode,
            "message": message,
            "ok_message": ok_message,
            **ctx,
        },
    )


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/competitions", status_code=303)
    return RedirectResponse("/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/competitions", status_code=303)
    return _auth_page(request, "signin")


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/competitions", status_code=303)
    return _auth_page(request, "signup")


@router.get("/reset", response_class=HTMLResponse)
async def reset_page(request: Request):
    return _auth_page(request, "reset_request")


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(or_(User.login == identifier, User.email == identifier))
        .first()
    )
    if user is None or not verify_password(password, user.password_hash):
        return _auth_page(
            request, "signin", "Taki użytkownik nie istnieje lub hasło jest błędne."
        )
    resp = RedirectResponse("/competitions", status_code=303)
    resp.set_cookie(
        settings.session_cookie,
        make_session_token(user.id),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return resp


@router.post("/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    login: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    repeat_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != repeat_password:
        return _auth_page(request, "signup", "Hasła nie są identyczne.")
    if len(password) < 6:
        return _auth_page(request, "signup", "Hasło musi mieć co najmniej 6 znaków.")
    exists = (
        db.query(User)
        .filter(or_(User.login == login, User.email == email))
        .first()
    )
    if exists:
        return _auth_page(
            request, "signup", "Użytkownik o takim loginie lub e-mailu już istnieje."
        )
    user = User(login=login, email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    resp = RedirectResponse("/competitions", status_code=303)
    resp.set_cookie(
        settings.session_cookie,
        make_session_token(user.id),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(settings.session_cookie)
    return resp


# ---- password reset flow ----


@router.post("/reset/request", response_class=HTMLResponse)
async def reset_request(
    request: Request, email: str = Form(...), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        return _auth_page(
            request, "reset_request", "Nie ma użytkownika z takim adresem e-mail."
        )
    code = new_reset_code()
    db.add(PasswordReset(user_id=user.id, code=code))
    db.commit()
    send_reset_code(user.email, code)
    return _auth_page(
        request,
        "reset_verify",
        "Wysłaliśmy na Twój e-mail kod. Wprowadź go poniżej.",
        ok_message=True,
        email=email,
    )


@router.post("/reset/verify", response_class=HTMLResponse)
async def reset_verify(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    pr = None
    if user:
        pr = (
            db.query(PasswordReset)
            .filter_by(user_id=user.id, code=code.strip(), used=False)
            .order_by(PasswordReset.id.desc())
            .first()
        )
    if pr is None:
        return _auth_page(
            request, "reset_verify", "Kod jest nieprawidłowy.", email=email
        )
    return _auth_page(
        request,
        "reset_update",
        "Kod poprawny. Ustaw nowe hasło.",
        ok_message=True,
        email=email,
        code=code,
    )


@router.post("/reset/update", response_class=HTMLResponse)
async def reset_update(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    password: str = Form(...),
    repeat_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != repeat_password:
        return _auth_page(
            request, "reset_update", "Hasła nie są identyczne.", email=email, code=code
        )
    user = db.query(User).filter(User.email == email).first()
    pr = None
    if user:
        pr = (
            db.query(PasswordReset)
            .filter_by(user_id=user.id, code=code.strip(), used=False)
            .order_by(PasswordReset.id.desc())
            .first()
        )
    if pr is None:
        return _auth_page(request, "signin", "Sesja resetowania wygasła.")
    user.password_hash = hash_password(password)
    pr.used = True
    db.commit()
    return _auth_page(
        request,
        "signin",
        "Hasło zostało zmienione. Możesz się zalogować.",
        ok_message=True,
    )
