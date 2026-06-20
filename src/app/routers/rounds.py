"""Tournament rounds: create, render bracket form, generate, save."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Rights, ensure, require_user, rights_for
from app.models import AgeCategory, Competition, Participant, Round, WeightCategory
from app.routers.categories import load_weight
from app.services.brackets import build_empty_bracket, build_initial_bracket
from app.templating import templates

router = APIRouter()


def _ordered(weight: WeightCategory) -> list[Participant]:
    return sorted(
        weight.participants,
        key=lambda p: (p.order_index is None, p.order_index or 0, p.id),
    )


def _participants_payload(weight: WeightCategory) -> list[dict]:
    return [
        {
            "number": i + 1,
            "name": p.name,
            "year": p.birth_year,
            "team": p.team,
            "other": p.other_info,
        }
        for i, p in enumerate(_ordered(weight))
    ]


def _participant_map(weight: WeightCategory) -> dict[str, dict]:
    """draw number (as string, 1-based) -> participant data, for the Fillup button.

    The number is the persisted draw position (``order_index``); it stays stable
    after shuffling, so the referee can reference it in later rounds.
    """
    return {
        str(i + 1): {"name": p.name, "year": p.birth_year, "team": p.team}
        for i, p in enumerate(_ordered(weight))
    }


def load_round(
    round_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    rnd = db.get(Round, round_id)
    if rnd is None:
        raise HTTPException(404, "Runda nie istnieje")
    weight = db.get(WeightCategory, rnd.weight_category_id)
    age = db.get(AgeCategory, weight.age_category_id)
    comp = db.get(Competition, age.competition_id)
    rights = rights_for(db, user, comp)
    ensure(rights.can_read)
    return rnd, weight, comp, rights


@router.post("/weight-categories/{weight_category_id}/rounds")
async def create_round(
    loaded: tuple = Depends(load_weight),
    db: Session = Depends(get_db),
):
    weight, age, comp, rights = loaded
    ensure(rights.can_create)
    next_index = (max((r.index for r in weight.rounds), default=0)) + 1
    rnd = Round(weight_category_id=weight.id, index=next_index)
    if next_index == 1:
        payload = _participants_payload(weight)
        rnd.num_participants = len(payload)
        rnd.data = build_initial_bracket(payload)
    db.add(rnd)
    db.commit()
    return RedirectResponse(f"/weight-categories/{weight.id}", status_code=303)


@router.get("/rounds/{round_id}", response_class=HTMLResponse)
async def round_form(
    request: Request,
    loaded: tuple = Depends(load_round),
    db: Session = Depends(get_db),
):
    rnd, weight, comp, rights = loaded
    # Round 1 always reflects the current participant draw.
    if rnd.index == 1 and rnd.data is None:
        payload = _participants_payload(weight)
        rnd.num_participants = len(payload)
        rnd.data = build_initial_bracket(payload)
        db.commit()
    return templates.TemplateResponse(
        "partials/round_form.html",
        {
            "request": request,
            "round": rnd,
            "weight": weight,
            "rights": rights,
            "participant_map": _participant_map(weight),
        },
    )


@router.post("/rounds/{round_id}/generate", response_class=HTMLResponse)
async def generate_round(
    request: Request,
    count: int = Form(...),
    loaded: tuple = Depends(load_round),
    db: Session = Depends(get_db),
):
    rnd, weight, comp, rights = loaded
    ensure(rights.can_update)
    count = max(count, 0)
    rnd.num_participants = count
    rnd.data = build_empty_bracket(count)
    db.commit()
    return templates.TemplateResponse(
        "partials/round_form.html",
        {
            "request": request,
            "round": rnd,
            "weight": weight,
            "rights": rights,
            "participant_map": _participant_map(weight),
        },
    )


@router.post("/rounds/{round_id}/save", response_class=HTMLResponse)
async def save_round(
    request: Request,
    loaded: tuple = Depends(load_round),
    db: Session = Depends(get_db),
):
    rnd, weight, comp, rights = loaded
    ensure(rights.can_update)
    form = await request.form()
    raw = form.get("data")
    if raw:
        try:
            rnd.data = json.loads(raw)
        except json.JSONDecodeError:
            pass
    db.commit()
    return templates.TemplateResponse(
        "partials/round_form.html",
        {
            "request": request,
            "round": rnd,
            "weight": weight,
            "rights": rights,
            "saved": True,
            "participant_map": _participant_map(weight),
        },
    )


@router.post("/rounds/{round_id}/delete")
async def delete_round(
    loaded: tuple = Depends(load_round),
    db: Session = Depends(get_db),
):
    rnd, weight, comp, rights = loaded
    ensure(rights.can_delete)
    wid = weight.id
    db.delete(rnd)
    db.commit()
    return RedirectResponse(f"/weight-categories/{wid}", status_code=303)
