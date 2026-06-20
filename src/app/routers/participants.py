"""Weight-category page: participant table, shuffle and draw ordering."""
from __future__ import annotations

import json
import random

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ensure, require_user
from app.models import Participant, Round
from app.routers.categories import load_weight
from app.templating import templates

router = APIRouter()


def _ordered_participants(weight) -> list[Participant]:
    parts = list(weight.participants)
    parts.sort(key=lambda p: (p.order_index is None, p.order_index or 0, p.id))
    return parts


@router.get("/weight-categories/{weight_category_id}", response_class=HTMLResponse)
async def weight_category_page(
    request: Request,
    loaded: tuple = Depends(load_weight),
    user=Depends(require_user),
):
    weight, age, comp, rights = loaded
    return templates.TemplateResponse(
        "weight_category.html",
        {
            "request": request,
            "user": user,
            "competition": comp,
            "age": age,
            "weight": weight,
            "rights": rights,
            "participants": _ordered_participants(weight),
            "rounds": weight.rounds,
        },
    )


@router.post("/weight-categories/{weight_category_id}/participants/save")
async def save_participants(
    request: Request,
    loaded: tuple = Depends(load_weight),
    db: Session = Depends(get_db),
):
    weight, age, comp, rights = loaded
    ensure(rights.can_update)
    form = await request.form()
    # Existing rows: name_<id>, year_<id>, team_<id>, other_<id>
    for p in list(weight.participants):
        name = form.get(f"name_{p.id}")
        if name is None:
            continue
        if not name.strip():
            db.delete(p)
            continue
        p.name = name.strip()
        p.birth_year = _int(form.get(f"year_{p.id}"))
        p.team = (form.get(f"team_{p.id}") or "").strip() or None
        p.other_info = (form.get(f"other_{p.id}") or "").strip() or None
    # New rows: newname[] / newyear[] / newteam[] / newother[]
    new_names = form.getlist("newname")
    new_years = form.getlist("newyear")
    new_teams = form.getlist("newteam")
    new_others = form.getlist("newother")
    for i, nm in enumerate(new_names):
        if nm and nm.strip():
            db.add(
                Participant(
                    weight_category_id=weight.id,
                    name=nm.strip(),
                    birth_year=_int(new_years[i] if i < len(new_years) else None),
                    team=(new_teams[i].strip() if i < len(new_teams) and new_teams[i] else None),
                    other_info=(new_others[i].strip() if i < len(new_others) and new_others[i] else None),
                )
            )
    db.commit()
    return RedirectResponse(
        f"/weight-categories/{weight.id}", status_code=303
    )


@router.post("/weight-categories/{weight_category_id}/participants/{pid}/delete")
async def delete_participant(
    pid: int,
    loaded: tuple = Depends(load_weight),
    db: Session = Depends(get_db),
):
    weight, age, comp, rights = loaded
    ensure(rights.can_delete)
    p = db.get(Participant, pid)
    if p and p.weight_category_id == weight.id:
        db.delete(p)
        db.commit()
    return RedirectResponse(f"/weight-categories/{weight.id}", status_code=303)


@router.post("/weight-categories/{weight_category_id}/shuffle", response_class=HTMLResponse)
async def shuffle_participants(
    request: Request,
    loaded: tuple = Depends(load_weight),
    db: Session = Depends(get_db),
):
    weight, age, comp, rights = loaded
    ensure(rights.can_update)
    parts = list(weight.participants)
    random.shuffle(parts)
    for idx, p in enumerate(parts, start=1):
        p.order_index = idx
    db.commit()
    return templates.TemplateResponse(
        "partials/shuffle_table.html",
        {"request": request, "participants": parts, "weight": weight, "rights": rights},
    )


@router.post("/weight-categories/{weight_category_id}/order")
async def save_order(
    request: Request,
    loaded: tuple = Depends(load_weight),
    db: Session = Depends(get_db),
):
    weight, age, comp, rights = loaded
    ensure(rights.can_update)
    form = await request.form()
    order = form.get("order", "")
    ids = [int(x) for x in order.split(",") if x.strip().isdigit()]
    pos = {pid: i + 1 for i, pid in enumerate(ids)}
    for p in weight.participants:
        if p.id in pos:
            p.order_index = pos[p.id]
    db.commit()
    return RedirectResponse(f"/weight-categories/{weight.id}", status_code=303)


def _int(v):
    try:
        return int(float(str(v).strip())) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None
