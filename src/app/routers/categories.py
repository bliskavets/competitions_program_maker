"""Document upload, age categories and weight categories."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Rights, ensure, require_user, rights_for
from app.models import AgeCategory, Competition, User, WeightCategory
from app.services.excel_import import import_workbook
from app.templating import templates

router = APIRouter()


def load_age(
    age_category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> tuple[AgeCategory, Competition, Rights]:
    age = db.get(AgeCategory, age_category_id)
    if age is None:
        raise HTTPException(404, "Kategoria wiekowa nie istnieje")
    comp = db.get(Competition, age.competition_id)
    rights = rights_for(db, user, comp)
    ensure(rights.can_read)
    return age, comp, rights


def load_weight(
    weight_category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> tuple[WeightCategory, AgeCategory, Competition, Rights]:
    weight = db.get(WeightCategory, weight_category_id)
    if weight is None:
        raise HTTPException(404, "Kategoria wagowa nie istnieje")
    age = db.get(AgeCategory, weight.age_category_id)
    comp = db.get(Competition, age.competition_id)
    rights = rights_for(db, user, comp)
    ensure(rights.can_read)
    return weight, age, comp, rights


# ---- documents upload ----


@router.post("/competitions/{competition_id}/documents", response_class=HTMLResponse)
async def upload_documents(
    request: Request,
    competition_id: int,
    files: list[UploadFile] = [],  # noqa: B006 - FastAPI form binding
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    comp = db.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(404, "Soutěž nie istnieje")
    rights = rights_for(db, user, comp)
    ensure(rights.can_create or rights.can_update)

    total = 0
    errors: list[str] = []
    for f in files:
        if not f.filename:
            continue
        if not f.filename.lower().endswith((".xlsx", ".xlsm")):
            errors.append(f"{f.filename}: nieobsługiwany format (wymagany .xlsx)")
            continue
        data = await f.read()
        try:
            total += import_workbook(db, comp, data)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{f.filename}: {exc}")

    db.refresh(comp)
    return templates.TemplateResponse(
        "partials/upload_result.html",
        {
            "request": request,
            "added": total,
            "errors": errors,
            "competition": comp,
            "rights": rights,
            "age_categories": comp.age_categories,
        },
    )


# ---- age categories ----


@router.post("/competitions/{competition_id}/age-categories")
async def add_age_category(
    competition_id: int,
    min_year: int = Form(...),
    max_year: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    comp = db.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(404, "Soutěž nie istnieje")
    rights = rights_for(db, user, comp)
    ensure(rights.can_create)
    lo, hi = sorted((min_year, max_year))
    name = f"{lo}–{hi}"
    db.add(
        AgeCategory(
            competition_id=comp.id, min_birth_year=lo, max_birth_year=hi, name=name
        )
    )
    db.commit()
    return RedirectResponse(f"/competitions/{competition_id}", status_code=303)


@router.post("/age-categories/{age_category_id}/delete")
async def delete_age_category(
    age_category_id: int,
    loaded: tuple = Depends(load_age),
    db: Session = Depends(get_db),
):
    age, comp, rights = loaded
    ensure(rights.can_delete)
    cid = comp.id
    db.delete(age)
    db.commit()
    return RedirectResponse(f"/competitions/{cid}", status_code=303)


@router.get("/age-categories/{age_category_id}", response_class=HTMLResponse)
async def age_category_page(
    request: Request,
    loaded: tuple = Depends(load_age),
    user: User = Depends(require_user),
):
    age, comp, rights = loaded
    return templates.TemplateResponse(
        "age_category.html",
        {
            "request": request,
            "user": user,
            "competition": comp,
            "age": age,
            "rights": rights,
            "weight_categories": age.weight_categories,
        },
    )


# ---- weight categories ----


@router.post("/age-categories/{age_category_id}/weight-categories")
async def add_weight_category(
    age_category_id: int,
    weight: float = Form(...),
    loaded: tuple = Depends(load_age),
    db: Session = Depends(get_db),
):
    age, comp, rights = loaded
    ensure(rights.can_create)
    db.add(
        WeightCategory(
            age_category_id=age.id, weight=weight, name=f"{weight:g} kg"
        )
    )
    db.commit()
    return RedirectResponse(f"/age-categories/{age_category_id}", status_code=303)


@router.post("/weight-categories/{weight_category_id}/delete")
async def delete_weight_category(
    weight_category_id: int,
    loaded: tuple = Depends(load_weight),
    db: Session = Depends(get_db),
):
    weight, age, comp, rights = loaded
    ensure(rights.can_delete)
    aid = age.id
    db.delete(weight)
    db.commit()
    return RedirectResponse(f"/age-categories/{aid}", status_code=303)
