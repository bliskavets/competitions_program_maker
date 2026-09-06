"""Document upload, age categories and weight categories."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Rights, ensure, require_user, rights_for
from app.models import AgeCategory, Competition, User, WeightCategory
from app.services.excel_import import import_workbook, preview_workbook
from app.services.excel_template import render_import_template
from app.templating import templates

router = APIRouter()
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


@router.get("/competitions/{competition_id}/import-template.xlsx")
async def download_import_template(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    comp = db.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(404, "Zawody nie istnieją")
    rights = rights_for(db, user, comp)
    ensure(rights.can_read)
    return Response(
        render_import_template(comp),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="szablon_uczestnikow.xlsx"'},
    )


@router.post("/competitions/{competition_id}/documents", response_class=HTMLResponse)
async def upload_documents(
    request: Request,
    competition_id: int,
    files: list[UploadFile] = [],  # noqa: B006 - FastAPI form binding
    mode: str = Form("import"),
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
    file_data: list[tuple[str, bytes]] = []
    for f in files:
        if not f.filename:
            continue
        if not f.filename.lower().endswith((".xlsx", ".xlsm")):
            errors.append(f"{f.filename}: nieobsługiwany format (wymagany .xlsx)")
            continue
        data = await f.read()
        file_data.append((f.filename, data))

    if mode == "preview":
        allowed = {
            (age.name or "").casefold(): {
                (category.name or "").casefold()
                for category in age.weight_categories
                if category.name and not category.is_auto_grouped
            }
            for age in comp.age_categories
        }
        previews = []
        for filename, data in file_data:
            try:
                sheets = preview_workbook(data, allowed_categories=allowed)
                if not sheets:
                    errors.append(f"{filename}: nie znaleziono arkusza uczestników")
                previews.append({"filename": filename, "sheets": sheets})
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{filename}: {exc}")
        return templates.TemplateResponse(
            "partials/upload_preview.html",
            {"request": request, "previews": previews, "errors": errors},
        )

    for filename, data in file_data:
        try:
            total += import_workbook(db, comp, data)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append(f"{filename}: {exc}")

    db.refresh(comp)
    review_count = sum(
        1
        for age in comp.age_categories
        for category in age.weight_categories
        if category.needs_review
    )
    response = templates.TemplateResponse(
        "partials/upload_result.html",
        {
            "request": request,
            "added": total,
            "errors": errors,
            "competition": comp,
            "rights": rights,
            "age_categories": comp.age_categories,
            "review_count": review_count,
        },
    )
    response.headers["HX-Retarget"] = "#categories-area"
    response.headers["HX-Trigger"] = "documentsImported"
    return response


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
    review_only: bool = Query(False),
    loaded: tuple = Depends(load_age),
    user: User = Depends(require_user),
):
    age, comp, rights = loaded
    categories = list(age.weight_categories)
    problem_count = sum(1 for category in categories if category.needs_review)
    if review_only:
        categories = [category for category in categories if category.needs_review]
    return templates.TemplateResponse(
        "age_category.html",
        {
            "request": request,
            "user": user,
            "competition": comp,
            "age": age,
            "rights": rights,
            "weight_categories": categories,
            "review_only": review_only,
            "problem_count": problem_count,
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
