"""Weight-category page: participant table, shuffle and draw ordering."""
from __future__ import annotations

import random
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ensure, require_user
from app.models import Participant, WeightCategory
from app.routers.categories import load_weight
from app.services.child_grouping import group_children, normalize_gender
from app.templating import templates

router = APIRouter()


def _ordered_participants(weight) -> list[Participant]:
    parts = list(weight.participants)
    parts.sort(key=lambda p: (p.order_index is None, p.order_index or 0, p.id))
    return parts


def _move_targets(comp) -> list[WeightCategory]:
    return [
        category
        for age in comp.age_categories
        for category in age.weight_categories
    ]


@router.get("/weight-categories/{weight_category_id}", response_class=HTMLResponse)
async def weight_category_page(
    request: Request,
    order_saved: bool = False,
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
            "move_targets": _move_targets(comp),
            "order_saved": order_saved,
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
    affected_categories = {weight.id}
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
        p.gender = normalize_gender(form.get(f"gender_{p.id}"))
        p.actual_weight = _decimal(form.get(f"actual_weight_{p.id}"))
        p.team = (form.get(f"team_{p.id}") or "").strip() or None
        p.other_info = (form.get(f"other_{p.id}") or "").strip() or None
        target_id = _int(form.get(f"category_{p.id}"))
        if target_id and target_id != weight.id:
            target = db.get(WeightCategory, target_id)
            if (
                target is not None
                and target.age_category.competition_id == comp.id
            ):
                p.weight_category_id = target.id
                affected_categories.add(target.id)
    # New rows: newname[] / newyear[] / newteam[] / newother[]
    new_names = form.getlist("newname")
    new_years = form.getlist("newyear")
    new_genders = form.getlist("newgender")
    new_weights = form.getlist("newweight")
    new_teams = form.getlist("newteam")
    new_others = form.getlist("newother")
    for i, nm in enumerate(new_names):
        if nm and nm.strip():
            db.add(
                Participant(
                    weight_category_id=weight.id,
                    name=nm.strip(),
                    birth_year=_int(new_years[i] if i < len(new_years) else None),
                    gender=normalize_gender(
                        new_genders[i] if i < len(new_genders) else None
                    ),
                    actual_weight=_decimal(new_weights[i] if i < len(new_weights) else None),
                    team=(new_teams[i].strip() if i < len(new_teams) and new_teams[i] else None),
                    other_info=(new_others[i].strip() if i < len(new_others) and new_others[i] else None),
                )
            )
    db.flush()
    for category_id in affected_categories:
        _refresh_auto_category(db, category_id)
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
    ordered_values = form.getlist("participant_id")
    if ordered_values:
        ids = [int(value) for value in ordered_values if value.isdigit()]
    else:
        order = form.get("order", "")
        ids = [int(x) for x in order.split(",") if x.strip().isdigit()]
    pos = {pid: i + 1 for i, pid in enumerate(ids)}
    for p in weight.participants:
        if p.id in pos:
            p.order_index = pos[p.id]
    db.commit()
    return RedirectResponse(
        f"/weight-categories/{weight.id}?order_saved=1", status_code=303
    )


def _int(v):
    try:
        return int(float(str(v).strip())) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _decimal(v):
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).strip().replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _refresh_auto_category(db: Session, category_id: int) -> None:
    category = db.get(WeightCategory, category_id)
    if category is None or not category.is_auto_grouped:
        return
    participants = list(
        db.scalars(select(Participant).where(Participant.weight_category_id == category_id))
    )
    reference_year = (
        category.age_category.competition.event_date or date.today()
    ).year
    suggested_groups = group_children(participants, reference_year=reference_year)
    weights = [participant.actual_weight for participant in participants]
    known = [value for value in weights if value is not None]
    category.needs_review = (
        len(suggested_groups) != 1
        or suggested_groups[0].needs_review
    )
    if known:
        if len(suggested_groups) == 1:
            current_number = re.search(r"Grupa\s+(\d+)", category.name or "")
            category.name = re.sub(
                r"Grupa\s+\d+",
                f"Grupa {current_number.group(1)}" if current_number else "Grupa 1",
                suggested_groups[0].name,
                count=1,
            )
        else:
            prefix_match = re.match(r"^(.*?Grupa\s+\d+)", category.name or "")
            prefix = prefix_match.group(1) if prefix_match else "Grupa"
            lo, hi = _format_weight(min(known)), _format_weight(max(known))
            category.name = (
                f"{prefix} · {lo} kg" if lo == hi else f"{prefix} · {lo}–{hi} kg"
            )
        category.weight = float((min(known) + max(known)) / 2)


def _format_weight(value: Decimal | float) -> str:
    number = Decimal(str(value)).quantize(Decimal("0.01"))
    return format(number, "f").rstrip("0").rstrip(".").replace(".", ",")
