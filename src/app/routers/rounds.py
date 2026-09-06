"""Tournament rounds: create, render bracket form, generate, save."""
from __future__ import annotations

import json
from copy import deepcopy

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Rights, ensure, require_user, rights_for
from app.models import AgeCategory, Bout, Competition, Participant, Round, WeightCategory
from app.routers.categories import load_weight
from app.services.brackets import build_empty_bracket, build_initial_bracket, normalize_bracket
from app.services.results import recalculate, set_winner, sync_bouts
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
            "id": p.id,
            "number": i + 1,
            "name": p.name,
            "year": p.birth_year,
            "team": p.team,
            "other": p.other_info,
            "actual_weight": float(p.actual_weight) if p.actual_weight is not None else None,
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


def prepare_round(db: Session, rnd: Round, weight: WeightCategory) -> dict:
    """Upgrade old JSON, recover participant ids and prepare online results."""
    if rnd.data is None:
        return {"groups": [], "standings": [], "bouts": [], "complete": False}
    data = normalize_bracket(rnd.data)
    participants_by_name: dict[str, list[Participant]] = {}
    for participant in weight.participants:
        participants_by_name.setdefault(participant.name, []).append(participant)
    for group in data.get("groups") or []:
        for row in group.get("rows") or []:
            if row.get("participant_id") is not None:
                continue
            matches = participants_by_name.get(row.get("name") or "", [])
            if len(matches) == 1:
                row["participant_id"] = matches[0].id
    if data != rnd.data:
        rnd.data = deepcopy(data)
        db.flush()
    sync_bouts(db, rnd)
    return recalculate(db, rnd)


def _round_context(
    request: Request,
    rnd: Round,
    weight: WeightCategory,
    rights: Rights,
    db: Session,
    **extra,
) -> dict:
    return {
        "request": request,
        "round": rnd,
        "weight": weight,
        "rights": rights,
        "participant_map": _participant_map(weight),
        "results": prepare_round(db, rnd, weight),
        **extra,
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
    db.flush()
    if rnd.data is not None:
        sync_bouts(db, rnd)
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
    context = _round_context(request, rnd, weight, rights, db)
    db.commit()
    return templates.TemplateResponse("partials/round_form.html", context)


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
    db.flush()
    context = _round_context(request, rnd, weight, rights, db)
    db.commit()
    return templates.TemplateResponse("partials/round_form.html", context)


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
    db.flush()
    context = _round_context(request, rnd, weight, rights, db, saved=True)
    db.commit()
    return templates.TemplateResponse("partials/round_form.html", context)


def load_bout(
    bout_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    bout = db.get(Bout, bout_id)
    if bout is None:
        raise HTTPException(404, "Walka nie istnieje")
    rnd = db.get(Round, bout.round_id)
    weight = db.get(WeightCategory, rnd.weight_category_id)
    age = db.get(AgeCategory, weight.age_category_id)
    comp = db.get(Competition, age.competition_id)
    rights = rights_for(db, user, comp)
    ensure(rights.can_read)
    return bout, rnd, weight, rights


@router.post("/bouts/{bout_id}/winner", response_class=HTMLResponse)
async def update_bout_winner(
    request: Request,
    winner_id: str = Form(""),
    loaded: tuple = Depends(load_bout),
    db: Session = Depends(get_db),
):
    bout, rnd, weight, rights = loaded
    ensure(rights.can_update)
    try:
        selected = int(winner_id) if winner_id else None
        set_winner(db, bout, selected)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    recalculate(db, rnd)
    db.flush()
    context = _round_context(request, rnd, weight, rights, db, saved=True)
    db.commit()
    return templates.TemplateResponse("partials/round_form.html", context)


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
