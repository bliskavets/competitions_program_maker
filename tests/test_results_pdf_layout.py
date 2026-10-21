"""Check text positions in the exported PDF, not just its file signature."""
import io
import re

import pytest
from pypdf import PdfReader
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics

from app.services.exports_pdf import (
    FONT,
    render_competition_results_pdf,
    render_results_pdf,
)


def _text_fragments(page):
    fragments = []

    def collect(text, cm, tm, font, size):
        # All result-table text uses translations, without rotation/scaling.
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        for line in text.splitlines():
            if line.strip():
                fragments.append((line, x, size))

    page.extract_text(visitor_text=collect)
    return fragments


def test_competition_results_category_does_not_overlap_place():
    category = "Chłopcy · 6–8 lat · Grupa 4 · 23–24,5 kg"
    pdf = render_competition_results_pdf(
        [{"age": "Dzieci", "weight": category, "place": 1, "name": "Maks Kowalczyk"}],
        title="Wyniki zawodów",
    )
    fragments = _text_fragments(PdfReader(io.BytesIO(pdf)).pages[0])
    place_x = next(x for text, x, _ in fragments if text == "1")
    category_fragments = [
        (text, x, size)
        for text, x, size in fragments
        if text.strip() in category and text.strip() != "1"
    ]
    assert category_fragments
    for text, x, size in category_fragments:
        assert x + pdfmetrics.stringWidth(text, FONT, size) < place_x - 4


@pytest.mark.parametrize("length", [255, 2000, 15000])
def test_competition_results_wraps_all_text_columns_and_splits_large_rows(length):
    pdf = render_competition_results_pdf(
        [{
            "age": "A" * length,
            "weight": "W" * length,
            "place": 1,
            "name": "N" * length,
        }]
    )
    reader = PdfReader(io.BytesIO(pdf))
    counts = {"A": 0, "W": 0, "N": 0}
    for page in reader.pages:
        fragments = _text_fragments(page)
        # Column starts come from rendered headers, independently of the layout code.
        weight_x = next(x for text, x, _ in fragments if text == "Kategoria wagowa")
        name_x = next(x for text, x, _ in fragments if text == "Nazwisko i imię")
        place_x = next(x for text, x, _ in fragments if text == "M-ce")
        right_edges = {
            "A": weight_x - 6,
            "W": place_x - 6,
            "N": float(page.mediabox.right) - 10 * mm - 6,
        }
        for text, x, size in fragments:
            if len(set(text)) != 1 or text[0] not in counts:
                continue
            marker = text[0]
            counts[marker] += len(text)
            assert size == 9
            right = x + pdfmetrics.stringWidth(text, FONT, size)
            assert right <= right_edges[marker] + 0.1
            if marker == "N":
                assert x >= name_x - 0.1
    assert counts == {"A": length, "W": length, "N": length}
    if length == 15000:
        assert len(reader.pages) > 1


def test_competition_results_repeats_headers_and_preserves_rows_across_pages():
    rows = [
        {
            "age": "Dzieci",
            "weight": "Bardzo długa kategoria wagowa " * 6,
            "place": index % 3 + 1,
            "name": f"Uczestnik {index:03d}",
        }
        for index in range(80)
    ]
    reader = PdfReader(io.BytesIO(render_competition_results_pdf(rows)))
    assert len(reader.pages) > 1
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert sorted(re.findall(r"Uczestnik \d{3}", text)) == [row["name"] for row in rows]
    for page in reader.pages:
        assert "Kategoria wiekowa" in page.extract_text()
        assert "Kategoria wagowa" in page.extract_text()


def test_results_preserves_literal_markup_and_newlines():
    literal = "<b>Klub & Szkoła</b>"
    rows = [{
        "age": literal,
        "weight": "Pierwsza linia\nDruga linia",
        "place": 1,
        "name": literal,
    }]
    combined = PdfReader(
        io.BytesIO(render_competition_results_pdf(rows, title=literal))
    ).pages[0].extract_text()
    assert combined.count(literal) == 3
    assert "Pierwsza linia\nDruga linia" in combined

    individual = PdfReader(
        io.BytesIO(render_results_pdf([{"place": 1, "name": literal}], title=literal))
    ).pages[0].extract_text()
    assert individual.count(literal) == 2


def test_individual_results_keeps_long_names_inside_the_page():
    name = "N" * 1000
    reader = PdfReader(io.BytesIO(render_results_pdf([{"place": 1, "name": name}])))
    count = 0
    for page in reader.pages:
        for text, x, size in _text_fragments(page):
            if set(text) != {"N"}:
                continue
            count += len(text)
            assert size == 11
            right_edge = float(page.mediabox.right) - 18 * mm - 6
            assert x + pdfmetrics.stringWidth(text, FONT, size) <= right_edge + 0.1
    assert count == len(name)
