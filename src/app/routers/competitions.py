"""Competitions list, create, delete, share, and the competition page."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import Rights, ensure, load_competition, require_user, rights_for
from app.models import Competition, CompetitionPermission, User
from app.templating import templates

router = APIRouter()


def _visible_competitions(db: Session, user: User):
    """Competitions the user owns or has been granted read access to."""
    shared_ids = [
        p.competition_id
        for p in db.query(CompetitionPermission)
        .filter_by(user_id=user.id, can_read=True)
        .all()
    ]
    return (
        db.query(Competition)
        .filter(
            or_(
                Competition.owner_id == user.id,
                Competition.id.in_(shared_ids) if shared_ids else False,
            )
        )
        .order_by(Competition.created_at.desc(), Competition.id.desc())
    )


@router.get("/competitions", response_class=HTMLResponse)
async def list_competitions(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    q = _visible_competitions(db, user)
    total = q.count()
    size = settings.page_size
    pages = max((total + size - 1) // size, 1)
    page = min(page, pages)
    items = q.offset((page - 1) * size).limit(size).all()
    return templates.TemplateResponse(
        "competitions.html",
        {
            "request": request,
            "user": user,
            "competitions": items,
            "page": page,
            "pages": pages,
            "total": total,
        },
    )


@router.post("/competitions", response_class=HTMLResponse)
async def create_competition(
    request: Request,
    name: str = Form(...),
    event_date: str = Form(""),
    birth_years: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    parsed_date: date | None = None
    if event_date:
        try:
            parsed_date = datetime.strptime(event_date, "%Y-%m-%d").date()
        except ValueError:
            parsed_date = None
    comp = Competition(
        name=name,
        event_date=parsed_date,
        birth_years=birth_years or None,
        description=description or None,
        owner_id=user.id,
    )
    db.add(comp)
    db.commit()
    return RedirectResponse(f"/competitions/{comp.id}", status_code=303)


@router.post("/competitions/{competition_id}/delete")
async def delete_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    loaded: tuple[Competition, Rights] = Depends(load_competition),
):
    comp, rights = loaded
    ensure(rights.can_delete)
    db.delete(comp)
    db.commit()
    return RedirectResponse("/competitions", status_code=303)


@router.post("/competitions/{competition_id}/share", response_class=HTMLResponse)
async def share_competition(
    request: Request,
    competition_id: int,
    target: str = Form(...),
    level: str = Form("read"),
    db: Session = Depends(get_db),
    loaded: tuple[Competition, Rights] = Depends(load_competition),
):
    comp, rights = loaded
    ensure(rights.is_owner or rights.can_update)
    target_user = (
        db.query(User)
        .filter(or_(User.login == target, User.email == target))
        .first()
    )
    if target_user is None:
        return templates.TemplateResponse(
            "partials/share_result.html",
            {"request": request, "ok": False, "message": "Nie ma takiego użytkownika."},
        )
    perm = (
        db.query(CompetitionPermission)
        .filter_by(competition_id=comp.id, user_id=target_user.id)
        .first()
    )
    if perm is None:
        perm = CompetitionPermission(
            competition_id=comp.id, user_id=target_user.id
        )
        db.add(perm)
    perm.can_read = True
    if level == "edit":
        perm.can_create = perm.can_update = perm.can_delete = True
    else:
        perm.can_create = perm.can_update = perm.can_delete = False
    db.commit()
    return templates.TemplateResponse(
        "partials/share_result.html",
        {
            "request": request,
            "ok": True,
            "message": f"Udostępniono użytkownikowi {target_user.login} "
            f"({'edycja' if level == 'edit' else 'odczyt'}).",
        },
    )


@router.get("/competitions/{competition_id}", response_class=HTMLResponse)
async def competition_page(
    request: Request,
    competition_id: int,
    db: Session = Depends(get_db),
    loaded: tuple[Competition, Rights] = Depends(load_competition),
    user: User = Depends(require_user),
):
    comp, rights = loaded
    return templates.TemplateResponse(
        "competition.html",
        {
            "request": request,
            "user": user,
            "competition": comp,
            "rights": rights,
            "age_categories": comp.age_categories,
        },
    )
