"""Download tournament sheets as A4 Excel / PDF (view + judging variants)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.routers.rounds import load_round
from app.services.brackets import build_empty_bracket
from app.services.exports_excel import render_bracket_xlsx
from app.services.exports_pdf import render_bracket_pdf

router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _bracket_and_title(rnd, weight):
    data = rnd.data or build_empty_bracket(rnd.num_participants or 0)
    title = (
        f"{weight.age_category.competition.name} — "
        f"{weight.age_category.name or ''} {weight.name or ''} "
        f"(Runda {rnd.index})"
    ).strip()
    return data, title


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
