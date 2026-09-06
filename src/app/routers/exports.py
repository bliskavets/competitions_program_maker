"""Download tournament sheets as A4 Excel / PDF (view + judging variants)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import load_competition
from app.routers.rounds import load_round, prepare_round
from app.services.brackets import build_empty_bracket, normalize_bracket
from app.services.exports_excel import (
    render_bracket_xlsx,
    render_competition_results_xlsx,
    render_results_xlsx,
)
from app.services.exports_pdf import (
    render_bracket_pdf,
    render_competition_results_pdf,
    render_results_pdf,
)

router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _bracket_and_title(rnd, weight):
    data = normalize_bracket(rnd.data) if rnd.data else build_empty_bracket(rnd.num_participants or 0)
    title = (
        f"{weight.age_category.competition.name} — "
        f"{weight.age_category.name or ''} {weight.name or ''} "
        f"(Runda {rnd.index})"
    ).strip()
    return data, title


def _completed_results(db: Session, rnd, weight) -> tuple[list[dict], str]:
    results = prepare_round(db, rnd, weight)
    if not results["standings"]:
        raise HTTPException(409, "Klasyfikacja nie jest jeszcze gotowa")
    _, title = _bracket_and_title(rnd, weight)
    return results["standings"], f"{title} — klasyfikacja końcowa"


def _competition_results(db: Session, competition) -> list[dict]:
    rows: list[dict] = []
    for age in competition.age_categories:
        for weight in age.weight_categories:
            for rnd in sorted(weight.rounds, key=lambda item: item.index, reverse=True):
                result = prepare_round(db, rnd, weight)
                if not result["standings"]:
                    continue
                rows.extend(
                    {
                        "age": age.name or "",
                        "weight": weight.name or "",
                        "place": standing["place"],
                        "name": standing["name"],
                    }
                    for standing in result["standings"]
                )
                break
    if not rows:
        raise HTTPException(409, "Brak zakończonych kategorii")
    return rows


@router.get("/rounds/{round_id}/excel")
async def download_excel(loaded: tuple = Depends(load_round)):
    rnd, weight, comp, rights = loaded
    data, title = _bracket_and_title(rnd, weight)
    content = render_bracket_xlsx(data, title=title, judging=False)
    return Response(
        content,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="runda_{rnd.index}.xlsx"'},
    )


@router.get("/rounds/{round_id}/pdf")
async def download_pdf(loaded: tuple = Depends(load_round)):
    rnd, weight, comp, rights = loaded
    data, title = _bracket_and_title(rnd, weight)
    content = render_bracket_pdf(data, title=title, judging=False)
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="runda_{rnd.index}.pdf"'},
    )


@router.get("/rounds/{round_id}/excel-judgement")
async def download_excel_judgement(loaded: tuple = Depends(load_round)):
    rnd, weight, comp, rights = loaded
    data, title = _bracket_and_title(rnd, weight)
    content = render_bracket_xlsx(data, title=f"{title} — sędziowanie", judging=True)
    return Response(
        content,
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="runda_{rnd.index}_sedziowanie.xlsx"'
        },
    )


@router.get("/rounds/{round_id}/pdf-judgement")
async def download_pdf_judgement(loaded: tuple = Depends(load_round)):
    rnd, weight, comp, rights = loaded
    data, title = _bracket_and_title(rnd, weight)
    content = render_bracket_pdf(data, title=f"{title} — sędziowanie", judging=True)
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="runda_{rnd.index}_sedziowanie.pdf"'
        },
    )


@router.get("/rounds/{round_id}/results/excel")
async def download_results_excel(
    loaded: tuple = Depends(load_round), db: Session = Depends(get_db)
):
    rnd, weight, comp, rights = loaded
    standings, title = _completed_results(db, rnd, weight)
    content = render_results_xlsx(standings, title=title)
    db.commit()
    return Response(
        content,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="wyniki_{rnd.index}.xlsx"'},
    )


@router.get("/rounds/{round_id}/results/pdf")
async def download_results_pdf(
    loaded: tuple = Depends(load_round), db: Session = Depends(get_db)
):
    rnd, weight, comp, rights = loaded
    standings, title = _completed_results(db, rnd, weight)
    content = render_results_pdf(standings, title=title)
    db.commit()
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="wyniki_{rnd.index}.pdf"'},
    )


@router.get("/competitions/{competition_id}/results/excel")
async def download_competition_results_excel(
    loaded: tuple = Depends(load_competition), db: Session = Depends(get_db)
):
    competition, rights = loaded
    rows = _competition_results(db, competition)
    content = render_competition_results_xlsx(rows, title=f"{competition.name} — wyniki")
    db.commit()
    return Response(
        content,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="wyniki_zawodow.xlsx"'},
    )


@router.get("/competitions/{competition_id}/results/pdf")
async def download_competition_results_pdf(
    loaded: tuple = Depends(load_competition), db: Session = Depends(get_db)
):
    competition, rights = loaded
    rows = _competition_results(db, competition)
    content = render_competition_results_pdf(rows, title=f"{competition.name} — wyniki")
    db.commit()
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="wyniki_zawodow.pdf"'},
    )
