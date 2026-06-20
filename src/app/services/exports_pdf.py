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
from reportlab.graphics.shapes import Drawing, Line, Rect, String
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
    # compact headings so the whole sheet fits one A4
    styles["Title"].fontSize = 15
    styles["Title"].leading = 18
    styles["Title"].spaceAfter = 2
    styles["Heading3"].fontSize = 11
    styles["Heading3"].spaceBefore = 2
    styles["Heading3"].spaceAfter = 2
    story: list[Any] = []
    if title:
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 2 * mm))

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
        story.append(Spacer(1, 2 * mm))

    if bracket.get("final"):
        story.extend(_final_flow(bracket["final"], avail, styles))

    story.append(Spacer(1, 3 * mm))
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
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
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
    flow: list[Any] = [Spacer(1, 3 * mm), Paragraph("<b>FINAŁ</b>", styles["Heading3"])]

    tree = _final_tree_drawing(final)

    places = [["M-ce", "Nazwisko i imię"]] + [[p, ""] for p in final.get("places", [])]
    pt = Table(places, colWidths=[18 * mm, 58 * mm])
    pt.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
                ("FONTNAME", (0, 0), (-1, -1), FONT),
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    # Tree and the M-ce (places) table side by side, mirroring the printed sheet.
    combo = Table([[tree, pt]], colWidths=[tree.width + 4 * mm, 80 * mm])
    combo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow.append(combo)
    return flow


def _final_tree_drawing(final: dict[str, Any]) -> Drawing:
    """Draw the knockout tree (A1–B2, B1–A2 → final) with empty name boxes,
    mirroring the on-screen FINAŁ bracket. Coordinates are in millimetres."""
    M = mm
    PRIMARY = colors.HexColor("#b5121b")
    GREY = colors.HexColor("#999999")
    bw, bh = 40, 8            # seed/semi box size (mm) — compact to fit one A4
    sx = 11                   # x of seed boxes
    sf_x = 66                 # x of semifinal boxes
    fx, fbw, fbh = 120, 46, 11  # final box
    drawing = Drawing(168 * M, 52 * M)

    def box(x, y, w, h, *, accent=False):
        drawing.add(
            Rect(x * M, y * M, w * M, h * M, strokeColor=PRIMARY if accent else colors.black,
                 strokeWidth=1.4 if accent else 0.8, fillColor=colors.white)
        )

    def tag(x, y, text, color=PRIMARY, size=8, bold=True):
        drawing.add(
            String(x * M, y * M, text, fontName=FONT_BOLD if bold else FONT,
                   fontSize=size, fillColor=color)
        )

    def line(x1, y1, x2, y2):
        drawing.add(Line(x1 * M, y1 * M, x2 * M, y2 * M, strokeColor=colors.black, strokeWidth=0.8))

    # seed boxes + labels: pair 1 (A1,B2) high, pair 2 (B1,A2) low
    seeds = [("A1", 42), ("B2", 32), ("B1", 14), ("A2", 4)]
    for label, by in seeds:
        box(sx, by, bw, bh)
        tag(1, by + 2.5, label)

    def connector(top_mid, bot_mid, vbar, target_x, sf_y):
        mid = (top_mid + bot_mid) / 2
        line(sx + bw, top_mid, vbar, top_mid)
        line(sx + bw, bot_mid, vbar, bot_mid)
        line(vbar, bot_mid, vbar, top_mid)
        line(vbar, mid, target_x, mid)
        box(sf_x, sf_y, bw, bh)
        tag(sf_x + 2, sf_y + 2.5, "zwycięzca", GREY, 6.5)

    connector(46, 36, 60, sf_x, 37)   # SF1 mid = 41
    connector(18, 8, 60, sf_x, 9)     # SF2 mid = 13

    # final connector: SF1 (mid 41) + SF2 (mid 13) -> final box (mid 27)
    sf_r = sf_x + bw
    line(sf_r, 41, 113, 41)
    line(sf_r, 13, 113, 13)
    line(113, 13, 113, 41)
    line(113, 27, fx, 27)
    box(fx, 27 - fbh / 2, fbw, fbh, accent=True)
    tag(fx + 2, 27 + 1, "FINAŁ — 1. miejsce", PRIMARY, 6.5)

    return drawing
