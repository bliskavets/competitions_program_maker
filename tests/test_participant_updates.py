from datetime import date

from sqlalchemy import select

from app.models import AgeCategory, Competition, Participant, User, WeightCategory
from app.routers.participants import _refresh_auto_category
from tests.conftest import register


def _category_data(client, db):
    register(client, "owner", "owner@example.pl")
    owner = db.scalar(select(User).where(User.login == "owner"))
    competition = Competition(name="Puchar", owner_id=owner.id)
    age = AgeCategory(name="Dzieci", competition=competition)
    first = WeightCategory(name="Grupa 1", age_category=age)
    second = WeightCategory(name="Grupa 2", age_category=age)
    participants = [
        Participant(name=f"Dziecko {i}", actual_weight=20 + i, weight_category=first)
        for i in range(1, 4)
    ]
    db.add(competition)
    db.commit()
    return first, second, participants


def test_participant_can_be_weighed_and_moved_between_categories(client, db_session):
    first, second, participants = _category_data(client, db_session)
    participant = participants[0]
    response = client.post(
        f"/weight-categories/{first.id}/participants/save",
        data={
            f"name_{participant.id}": participant.name,
            f"year_{participant.id}": "2017",
            f"gender_{participant.id}": "female",
            f"actual_weight_{participant.id}": "24,35",
            f"team_{participant.id}": "UKS",
            f"other_{participant.id}": "",
            f"category_{participant.id}": str(second.id),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.expire_all()
    moved = db_session.get(Participant, participant.id)
    assert moved.weight_category_id == second.id
    assert float(moved.actual_weight) == 24.35
    assert moved.gender == "female"


def test_saved_shuffle_is_visible_after_page_reload(client, db_session):
    first, second, participants = _category_data(client, db_session)
    response = client.post(f"/weight-categories/{first.id}/shuffle")
    assert response.status_code == 200
    assert "Zapisz kolejność" in response.text

    ids = [participant.id for participant in reversed(participants)]
    saved = client.post(
        f"/weight-categories/{first.id}/order",
        data={"order": ",".join(map(str, ids))},
        follow_redirects=True,
    )
    assert "Kolejność została zapisana" in saved.text

    reloaded = client.get(f"/weight-categories/{first.id}")
    assert reloaded.status_code == 200
    assert "Zapisz kolejność" in reloaded.text
    assert 'id="draw-body"' in reloaded.text
    db_session.expire_all()
    ordered = list(
        db_session.scalars(
            select(Participant)
            .where(Participant.weight_category_id == first.id)
            .order_by(Participant.order_index)
        )
    )
    assert [participant.id for participant in ordered] == ids


def test_browser_form_order_is_saved_after_drag(client, db_session):
    first, second, participants = _category_data(client, db_session)
    client.post(f"/weight-categories/{first.id}/shuffle")
    ids = [
        participant.id
        for participant in (participants[1], participants[2], participants[0])
    ]

    response = client.post(
        f"/weight-categories/{first.id}/order",
        data={"participant_id": [str(participant_id) for participant_id in ids]},
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.expire_all()
    ordered = list(
        db_session.scalars(
            select(Participant)
            .where(Participant.weight_category_id == first.id)
            .order_by(Participant.order_index)
        )
    )
    assert [participant.id for participant in ordered] == ids


def test_auto_group_refresh_preserves_number_and_flags_mixed_gender(db_session):
    owner = User(login="refresh-owner", email="refresh@test.pl", password_hash="x")
    competition = Competition(
        name="Puchar", event_date=date(2026, 12, 1), owner=owner
    )
    age = AgeCategory(name="Dzieci", competition=competition)
    category = WeightCategory(
        name="Chłopcy · 6–8 lat · Grupa 2 · 20–21 kg",
        age_category=age,
        is_auto_grouped=True,
    )
    participants = [
        Participant(
            name=f"Dziecko {index}",
            birth_year=2020,
            gender="male",
            actual_weight=20 + index / 10,
            weight_category=category,
        )
        for index in range(4)
    ]
    db_session.add(competition)
    db_session.flush()

    _refresh_auto_category(db_session, category.id)
    assert "Grupa 2" in category.name
    assert category.needs_review is False

    participants[0].gender = "female"
    _refresh_auto_category(db_session, category.id)
    assert category.needs_review is True
