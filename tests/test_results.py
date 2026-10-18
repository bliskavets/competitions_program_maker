from datetime import date

import pytest
from sqlalchemy import select

from app.models import (
    AgeCategory,
    Bout,
    Competition,
    Participant,
    Round,
    User,
    WeightCategory,
)
from app.services.brackets import build_initial_bracket
from app.services.results import create_tiebreak, recalculate, set_winner, sync_bouts


def _round(db, count: int) -> tuple[Round, list[Participant]]:
    user = User(login="owner", email="owner@example.pl", password_hash="x")
    comp = Competition(name="Puchar", event_date=date(2026, 8, 29), owner=user)
    age = AgeCategory(name="Dzieci", competition=comp)
    weight = WeightCategory(name="test", age_category=age)
    participants = [
        Participant(name=f"Zawodnik {i}", weight_category=weight, order_index=i)
        for i in range(1, count + 1)
    ]
    db.add(comp)
    db.flush()
    payload = [
        {"id": participant.id, "name": participant.name, "number": i}
        for i, participant in enumerate(participants, start=1)
    ]
    rnd = Round(
        weight_category=weight,
        index=1,
        num_participants=count,
        data=build_initial_bracket(payload),
    )
    db.add(rnd)
    db.flush()
    return rnd, participants


def _bout(db, rnd: Round, key: str) -> Bout:
    return db.scalar(select(Bout).where(Bout.round_id == rnd.id, Bout.key == key))


def _win_duel(db, bouts: list[Bout], first: Participant, second: Participant, winner: Participant):
    bout = next(
        bout
        for bout in bouts
        if {bout.player_a_id, bout.player_b_id} == {first.id, second.id}
    )
    set_winner(db, bout, winner.id)


def test_round_robin_results_are_persisted_and_ranked(db_session):
    rnd, participants = _round(db_session, 4)
    sync_bouts(db_session, rnd)
    bouts = list(db_session.scalars(select(Bout).where(Bout.round_id == rnd.id)))
    assert len(bouts) == 6

    # Lower draw number wins every direct duel, yielding an unambiguous table.
    for bout in bouts:
        set_winner(db_session, bout, min(bout.player_a_id, bout.player_b_id))
    result = recalculate(db_session, rnd)

    assert result["complete"] is True
    assert [row["participant_id"] for row in result["standings"]] == [p.id for p in participants]
    assert [row["place"] for row in result["standings"]] == [1, 2, 3, 3]


def test_winner_must_belong_to_bout(db_session):
    rnd, participants = _round(db_session, 3)
    sync_bouts(db_session, rnd)
    bout = db_session.scalar(select(Bout).where(Bout.round_id == rnd.id))
    with pytest.raises(ValueError):
        set_winner(db_session, bout, 999999)


def test_five_children_share_three_bronze_medals(db_session):
    rnd, participants = _round(db_session, 5)
    sync_bouts(db_session, rnd)
    for bout in db_session.scalars(select(Bout).where(Bout.round_id == rnd.id)):
        set_winner(db_session, bout, min(bout.player_a_id, bout.player_b_id))
    result = recalculate(db_session, rnd)
    assert [row["place"] for row in result["standings"]] == [1, 2, 3, 3, 3]


def test_cyclic_three_person_tie_creates_and_resolves_round_robin_replay(db_session):
    rnd, participants = _round(db_session, 4)
    sync_bouts(db_session, rnd)
    bouts = list(
        db_session.scalars(
            select(Bout).where(Bout.round_id == rnd.id, Bout.stage == "group")
        )
    )
    leader, second, third, fourth = participants
    for opponent in (second, third, fourth):
        _win_duel(db_session, bouts, leader, opponent, leader)
    _win_duel(db_session, bouts, second, third, second)
    _win_duel(db_session, bouts, third, fourth, third)
    _win_duel(db_session, bouts, fourth, second, fourth)

    tied = recalculate(db_session, rnd)
    assert tied["complete"] is False
    assert tied["standings"] == []
    assert len(tied["ties"]) == 1
    assert tied["ties"][0]["status"] == "needed"
    assert set(tied["ties"][0]["participant_ids"]) == {second.id, third.id, fourth.id}
    assert [row["place"] for row in tied["groups"][0]["ranking"]] == [1, None, None, None]

    replay = create_tiebreak(
        db_session, rnd, "S", tied["ties"][0]["participant_ids"]
    )
    assert len(replay) == 3
    _win_duel(db_session, replay, second, third, second)
    _win_duel(db_session, replay, second, fourth, second)
    _win_duel(db_session, replay, third, fourth, third)

    result = recalculate(db_session, rnd)
    assert result["complete"] is True
    assert [row["participant_id"] for row in result["standings"]] == [
        leader.id,
        second.id,
        third.id,
        fourth.id,
    ]
    assert [row["place"] for row in result["standings"]] == [1, 2, 3, 3]


def test_repeated_cyclic_tie_offers_another_replay(db_session):
    rnd, participants = _round(db_session, 3)
    sync_bouts(db_session, rnd)
    bouts = list(
        db_session.scalars(
            select(Bout).where(Bout.round_id == rnd.id, Bout.stage == "group")
        )
    )
    first, second, third = participants
    _win_duel(db_session, bouts, first, second, first)
    _win_duel(db_session, bouts, second, third, second)
    _win_duel(db_session, bouts, third, first, third)
    state = recalculate(db_session, rnd)

    replay = create_tiebreak(db_session, rnd, "S", state["ties"][0]["participant_ids"])
    _win_duel(db_session, replay, first, second, first)
    _win_duel(db_session, replay, second, third, second)
    _win_duel(db_session, replay, third, first, third)
    repeated = recalculate(db_session, rnd)

    assert repeated["complete"] is False
    assert repeated["ties"][0]["status"] == "needed"
    second_replay = create_tiebreak(
        db_session, rnd, "S", repeated["ties"][0]["participant_ids"]
    )
    assert len(second_replay) == 3
    assert all("-TB-2-" in bout.key for bout in second_replay)


def test_group_winners_advance_to_final_and_two_bronzes(db_session):
    rnd, participants = _round(db_session, 6)
    sync_bouts(db_session, rnd)

    # Within A (1,2,3) and B (4,5,6), the lower id wins.
    group_bouts = list(
        db_session.scalars(
            select(Bout).where(Bout.round_id == rnd.id, Bout.stage == "group")
        )
    )
    for bout in group_bouts:
        set_winner(db_session, bout, min(bout.player_a_id, bout.player_b_id))
    recalculate(db_session, rnd)

    sf1, sf2 = _bout(db_session, rnd, "FINAL-SF1"), _bout(db_session, rnd, "FINAL-SF2")
    assert {sf1.player_a_id, sf1.player_b_id} == {participants[0].id, participants[4].id}
    assert {sf2.player_a_id, sf2.player_b_id} == {participants[1].id, participants[3].id}
    set_winner(db_session, sf1, participants[0].id)
    set_winner(db_session, sf2, participants[3].id)
    recalculate(db_session, rnd)

    final = _bout(db_session, rnd, "FINAL-GOLD")
    assert {final.player_a_id, final.player_b_id} == {participants[0].id, participants[3].id}
    set_winner(db_session, final, participants[0].id)
    result = recalculate(db_session, rnd)

    assert [(row["participant_id"], row["place"]) for row in result["standings"]] == [
        (participants[0].id, 1),
        (participants[3].id, 2),
        (participants[4].id, 3),
        (participants[1].id, 3),
    ]


def test_knockout_group_byes_advance_automatically(db_session):
    rnd, participants = _round(db_session, 11)
    sync_bouts(db_session, rnd)
    assert db_session.scalar(
        select(Bout).where(
            Bout.round_id == rnd.id,
            Bout.stage == "group_knockout",
            Bout.status == "automatic",
        ).limit(1)
    ) is not None

    for _ in range(20):
        recalculate(db_session, rnd)
        ready = list(
            db_session.scalars(
                select(Bout).where(
                    Bout.round_id == rnd.id,
                    Bout.stage.in_(("group", "group_knockout")),
                    Bout.player_a_id.is_not(None),
                    Bout.player_b_id.is_not(None),
                    Bout.winner_id.is_(None),
                )
            )
        )
        if not ready:
            break
        for bout in ready:
            set_winner(db_session, bout, min(bout.player_a_id, bout.player_b_id))
    result = recalculate(db_session, rnd)
    assert all(group["complete"] for group in result["groups"])
    semifinals = [bout for bout in result["bouts"] if bout["stage"] == "semifinal"]
    assert len(semifinals) == 2
    assert all(bout["ready"] for bout in semifinals)
