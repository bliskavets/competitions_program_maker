"""Shared FastAPI dependencies: current user and per-competition permissions."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Competition, CompetitionPermission, User
from app.security import read_session_token


class LoginRedirect(Exception):
    """Raised when an HTML page requires login; handled by an exception handler."""


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(settings.session_cookie)
    if not token:
        return None
    uid = read_session_token(token)
    if uid is None:
        return None
    return db.get(User, uid)


def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise LoginRedirect()
    return user


@dataclass
class Rights:
    can_create: bool = False
    can_update: bool = False
    can_read: bool = False
    can_delete: bool = False
    is_owner: bool = False


def rights_for(db: Session, user: User, competition: Competition) -> Rights:
    if competition.owner_id == user.id:
        return Rights(True, True, True, True, is_owner=True)
    perm = (
        db.query(CompetitionPermission)
        .filter_by(competition_id=competition.id, user_id=user.id)
        .first()
    )
    if perm is None:
        return Rights()
    return Rights(
        can_create=perm.can_create,
        can_update=perm.can_update,
        can_read=perm.can_read,
        can_delete=perm.can_delete,
    )


def load_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> tuple[Competition, Rights]:
    comp = db.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status_code=404, detail="Soutěž nie istnieje")
    rights = rights_for(db, user, comp)
    if not rights.can_read:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brak dostępu")
    return comp, rights


def ensure(rights_flag: bool) -> None:
    if not rights_flag:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Brak uprawnień"
        )
