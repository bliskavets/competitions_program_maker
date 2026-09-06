import io

from openpyxl import load_workbook
from sqlalchemy import select

from app.models import AgeCategory, Bout, Competition, Participant, Round, User, WeightCategory
from tests.conftest import register


def _online_round(client, db):
    register(client, "owner", "owner@example.pl")
    owner = db.scalar(select(User).where(User.login == "owner"))
    competition = Competition(name="Puchar", owner_id=owner.id)
    age = AgeCategory(name="Dzieci", competition=competition)
    weight = WeightCategory(name="Grupa 1", age_category=age)
    for index in range(1, 4):
        Participant(name=f"Zawodnik {index}", order_index=index, weight_category=weight)
    db.add(competition)
    db.commit()
    response = client.post(f"/weight-categories/{weight.id}/rounds", follow_redirects=False)
    assert response.status_code == 303
    db.expire_all()
    rnd = db.scalar(select(Round).where(Round.weight_category_id == weight.id))
    return rnd


def test_online_winners_complete_standings_and_result_exports(client, db_session):
    rnd = _online_round(client, db_session)
    bouts = list(
        db_session.scalars(
            select(Bout).where(Bout.round_id == rnd.id).order_by(Bout.sequence)
        )
    )
    assert len(bouts) == 3
    for bout in bouts:
        response = client.post(
            f"/bouts/{bout.id}/winner",
            data={"winner_id": min(bout.player_a_id, bout.player_b_id)},
        )
        assert response.status_code == 200

    page = client.get(f"/rounds/{rnd.id}")
    assert "Klasyfikacja końcowa" in page.text
    assert "Wyniki Excel" in page.text

    excel = client.get(f"/rounds/{rnd.id}/results/excel")
    assert excel.status_code == 200
    workbook = load_workbook(io.BytesIO(excel.content))
    assert workbook.active.title == "Wyniki"
    assert workbook.active["A3"].value == "M-ce"

    pdf = client.get(f"/rounds/{rnd.id}/results/pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    combined_excel = client.get(
        f"/competitions/{rnd.weight_category.age_category.competition_id}/results/excel"
    )
    assert combined_excel.status_code == 200
    assert load_workbook(io.BytesIO(combined_excel.content)).active.title == "Wyniki zawodów"
    combined_pdf = client.get(
        f"/competitions/{rnd.weight_category.age_category.competition_id}/results/pdf"
    )
    assert combined_pdf.status_code == 200
    assert combined_pdf.content[:4] == b"%PDF"


def test_online_result_rejects_outsider(client, db_session):
    rnd = _online_round(client, db_session)
    bout = db_session.scalar(select(Bout).where(Bout.round_id == rnd.id))
    response = client.post(f"/bouts/{bout.id}/winner", data={"winner_id": 999999})
    assert response.status_code == 400
