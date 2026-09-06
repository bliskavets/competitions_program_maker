"""Tests for Excel parsing and import."""
import io

import pytest
from openpyxl import Workbook

from app.models import AgeCategory, Competition, User, WeightCategory
from app.services.excel_import import import_workbook, parse_workbook, preview_workbook


def _wb_bytes():
    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("Kadeci")
    ws.append(["Name and Surname", "Year of Birth", "Weight category", "Team", "Pas"])
    ws.append(["Jan Nowak", 2011, "45 kg", "UKS Warszawa", "żółty"])
    ws.append(["Piotr Kowalski", 2012, "45 kg", "KS Kraków", None])
    ws.append([None, None, None, None, None])  # blank row ignored
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_workbook_columns_and_other():
    sheets = parse_workbook(_wb_bytes())
    assert len(sheets) == 1
    sheet = sheets[0]
    assert sheet.age_category == "Kadeci"
    assert len(sheet.participants) == 2
    p = sheet.participants[0]
    assert p.name == "Jan Nowak"
    assert p.year == 2011
    assert p.weight == "45 kg"
    assert p.actual_weight is None
    assert p.team == "UKS Warszawa"
    # extra column folded into "other"
    assert "Pas" in p.other


def test_parse_polish_headers():
    wb = Workbook()
    ws = wb.active
    ws.title = "Młodzicy"
    ws.append(["Nazwisko i imię", "Rok", "Kategoria wagowa", "Klub"])
    ws.append(["Maja Wójcik", 2014, "30 kg", "AZS Wrocław"])
    buf = io.BytesIO()
    wb.save(buf)
    sheets = parse_workbook(buf.getvalue())
    assert sheets[0].participants[0].name == "Maja Wójcik"
    assert sheets[0].participants[0].weight == "30 kg"


def test_fixed_category_keeps_optional_measured_weight_separate():
    wb = Workbook()
    ws = wb.active
    ws.title = "Kadeci"
    ws.append(["Name and Surname", "Weight category", "Actual weight", "Team"])
    ws.append(["Jan Nowak", "45 kg", "43,75", "UKS"])
    buf = io.BytesIO()
    wb.save(buf)

    participant = parse_workbook(buf.getvalue())[0].participants[0]
    assert participant.weight == "45 kg"
    assert participant.actual_weight == 43.75


def test_children_import_groups_by_measured_weight(db_session):
    wb = Workbook()
    ws = wb.active
    ws.title = "Dzieci (2016-2017)"
    ws.append(["Name and Surname", "Year of Birth", "Weight category", "Team"])
    for i, weight in enumerate((20, 20.5, 20.8, 21, 21.3, 21.8, 22, 22.2), start=1):
        ws.append([f"Dziecko {i}", 2016 + i % 2, weight, "UKS"])
    buf = io.BytesIO()
    wb.save(buf)

    user = User(login="owner", email="owner@test.pl", password_hash="x")
    db_session.add(user)
    db_session.flush()
    competition = Competition(name="Cup", owner_id=user.id)
    db_session.add(competition)
    db_session.commit()
    db_session.refresh(competition)

    assert import_workbook(db_session, competition, buf.getvalue()) == 8
    age = competition.age_categories[0]
    assert [len(category.participants) for category in age.weight_categories] == [4, 4]
    assert all(category.is_auto_grouped for category in age.weight_categories)
    assert all(p.actual_weight is not None for category in age.weight_categories for p in category.participants)


def test_import_preview_reports_groups_and_invalid_rows():
    wb = Workbook()
    ws = wb.active
    ws.title = "Dzieci"
    ws.append(["Name and Surname", "Weight category", "Team"])
    for index, weight in enumerate((20, 20.5, 21, 21.5, None), start=1):
        ws.append([f"Dziecko {index}", weight, "UKS"])
    buf = io.BytesIO()
    wb.save(buf)

    sheet = preview_workbook(buf.getvalue())[0]
    assert sheet["participant_count"] == 5
    assert [group["count"] for group in sheet["groups"]] == [4, 1]
    assert "Wiersz 6" in sheet["issues"][0]


def test_configured_fixed_categories_reject_unknown_value(db_session):
    user = User(login="owner2", email="owner2@test.pl", password_hash="x")
    competition = Competition(name="Cup", owner=user)
    age = AgeCategory(name="Kadeci", competition=competition)
    WeightCategory(name="45 kg", weight=45, age_category=age)
    db_session.add(competition)
    db_session.commit()

    wb = Workbook()
    ws = wb.active
    ws.title = "Kadeci"
    ws.append(["Name and Surname", "Weight category", "Team"])
    ws.append(["Jan Nowak", "47 kg", "UKS"])
    buf = io.BytesIO()
    wb.save(buf)

    with pytest.raises(ValueError, match="spoza skonfigurowanej listy"):
        import_workbook(db_session, competition, buf.getvalue())
