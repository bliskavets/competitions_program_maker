"""Render tournament sheets to a single-A4 PDF with ReportLab.

Tables are scaled to fit the printable A4 width, mirroring the Excel layout.
The ``judging`` flag appends a ``Win`` column for the referee.
"""
from __future__ import annotations

import io
import os
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Paragraph,
)

# Register a Unicode font so Polish diacritics (ą, ę, ł, Ł, ś, ż, ...) render.
_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "fonts")
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
try:
    pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(
        TTFont("DejaVu-Bold", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf"))
    )
    pdfmetrics.registerFontFamily(
        "DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu", boldItalic="DejaVu-Bold"
    )
    FONT = "DejaVu"
    FONT_BOLD = "DejaVu-Bold"
except Exception:  # noqa: BLE001 - fall back to built-in fonts if TTF missing
    pass

REST_COLOR = colors.HexColor("#D9F2F2")
HEADER_COLOR = colors.HexColor("#E8E8E8")
BYE_TEXT = colors.HexColor("#888888")


def render_bracket_pdf(
    bracket: dict[str, Any],
    *,
    title: str = "",
    judging: bool = False,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=8 * mm,
        bottomMargin=8 * mm,
    )
    styles = getSampleStyleSheet()
    for name in ("Title", "Heading3", "Normal"):
        styles[name].fontName = FONT_BOLD if name != "Normal" else FONT
    story: list[Any] = []
    if title:
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 4 * mm))

    avail = doc.width

    groups = bracket.get("groups") or []
    if not groups and bracket.get("type") == "single_elim":
        groups = [bracket]

    for group in groups:
        gname = group.get("name")
        if gname:
            story.append(Paragraph(f"<b>Grupa {gname}</b>", styles["Heading3"]))
        if group.get("type") == "single_elim" or (
            "rounds" in group and "schedule" not in group
        ):
            story.append(_single_elim_table(group, avail, judging))
        else:
            story.append(_round_robin_table(group, avail, judging))
        story.append(Spacer(1, 4 * mm))

    if bracket.get("final"):
        story.extend(_final_flow(bracket["final"], avail, styles))

    story.append(Spacer(1, 6 * mm))
    footer = Table(
        [["Kierownik List", "", "Sędzia Główny"]],
        colWidths=[avail * 0.4, avail * 0.2, avail * 0.4],
    )
    footer.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, -1), FONT),
            ]
        )
    )
    story.append(footer)

    doc.build(story)
    return buf.getvalue()


def _round_robin_table(group: dict[str, Any], avail: float, judging: bool) -> Table:
    num_rounds = max(int(group.get("num_rounds", 0)), 1)
    headers = ["Lp.", "Nazwisko i imię", "Rok", "Klub"]
    headers += [str(i) for i in range(1, num_rounds + 1)]
    headers += ["suma\nPKT", "M-ce"]
    if judging:
        headers.append("Win")

    data = [headers]
    rest_cells: list[tuple[int, int]] = []
    for ridx, row in enumerate(group.get("rows", []), start=1):
        opponents = row.get("cells") or [None] * num_rounds
        round_cells = ["wl" if o is None else o for o in opponents]
        cells = [
            row.get("lp"),
            row.get("name"),
            row.get("year"),
            row.get("team") or "",
        ]
        cells += round_cells
        cells += ["", ""]
        if judging:
            cells.append("")
        for ci, val in enumerate(round_cells):
            if val == "wl":
                rest_cells.append((4 + ci, ridx))  # 0-based; rounds start at col 4
        data.append(cells)

    # column widths
    fixed = [10 * mm, 48 * mm, 12 * mm, 30 * mm]
    rest_w = avail - sum(fixed)
    n_small = num_rounds + 2 + (1 if judging else 0)
    small_w = max(rest_w / max(n_small, 1), 8 * mm)
    col_widths = fixed + [small_w] * n_small

    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for col, r in rest_cells:
        style.append(("BACKGROUND", (col, r), (col, r), REST_COLOR))
    table.setStyle(TableStyle(style))
    return table


def _single_elim_table(group: dict[str, Any], avail: float, judging: bool) -> Table:
    rounds = group.get("rounds", [])
    first = rounds[0]["matches"] if rounds else []
    data = [["Para", "Zawodnik (góra)", "Zawodnik (dół)"] + (["Win"] if judging else [])]
    bye_rows: list[int] = []
    for i, m in enumerate(first, start=1):
        top = m.get("top")
        bottom = m.get("bottom")
        if bottom is None:
            data.append([i, f"nr {top}", "wolny"] + ([""] if judging else []))
            bye_rows.append(i)
        else:
            data.append([i, f"nr {top}", f"nr {bottom}"] + ([""] if judging else []))
    ncols = 3 + (1 if judging else 0)
    table = Table(data, colWidths=[avail / ncols] * ncols, repeatRows=1)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]
    for r in bye_rows:
        style.append(("TEXTCOLOR", (0, r), (-1, r), BYE_TEXT))
    table.setStyle(TableStyle(style))
    return table


def _final_flow(final: dict[str, Any], avail: float, styles) -> list[Any]:
    flow: list[Any] = [Spacer(1, 4 * mm), Paragraph("<b>FINAŁ</b>", styles["Heading3"])]
    pairs = final.get("pairs", [])
    pair_data = [[a, "—", b] for a, b in pairs]
    if pair_data:
        t = Table(pair_data, colWidths=[avail * 0.25, avail * 0.1, avail * 0.25])
        t.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, -1), FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )
        flow.append(t)
    flow.append(Spacer(1, 3 * mm))
    places = [["M-ce", "Nazwisko i imię"]] + [[p, ""] for p in final.get("places", [])]
    pt = Table(places, colWidths=[avail * 0.12, avail * 0.5])
    pt.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
                ("FONTNAME", (0, 0), (-1, -1), FONT),
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    flow.append(pt)
    return flow
