"""Tests for the round-robin / bracket engine."""
from app.services.brackets import (
    build_empty_bracket,
    build_initial_bracket,
    round_robin_rounds,
    single_elimination,
)


def _people(n):
    return [{"name": f"Z{i}", "year": 2010, "team": "K"} for i in range(1, n + 1)]


def test_round_robin_every_pair_once():
    for n in range(2, 9):
        rounds = round_robin_rounds(n)
        pairs = set()
        for rnd in rounds:
            for a, b in rnd:
                if a is not None and b is not None:
                    pairs.add(frozenset((a, b)))
        # n*(n-1)/2 unique pairings
        assert len(pairs) == n * (n - 1) // 2


def test_round_robin_round_count():
    # even -> n-1 rounds, odd -> n rounds (one bye each)
    assert len(round_robin_rounds(4)) == 3
    assert len(round_robin_rounds(5)) == 5
    assert len(round_robin_rounds(6)) == 5


def test_small_group_is_round_robin():
    b = build_initial_bracket(_people(5))
    assert b["type"] == "single_group"
    assert len(b["groups"]) == 1
    assert b["final"] is None
    assert b["groups"][0]["num_participants"] == 5


def test_large_field_splits_into_two_groups_with_final():
    b = build_initial_bracket(_people(10))
    assert b["type"] == "groups"
    assert [g["name"] for g in b["groups"]] == ["A", "B"]
    assert b["final"]["pairs"] == [["A1", "B2"], ["B1", "A2"]]
    # two bronze (repechage)
    assert b["final"]["places"].count(3) == 2


def test_single_elimination_padding():
    se = single_elimination(6)
    assert se["bracket_size"] == 8
    assert se["byes"] == 2
    # first round has size/2 matches
    assert len(se["rounds"][0]["matches"]) == 4


def test_empty_bracket_small_is_round_robin():
    e = build_empty_bracket(4)
    assert e["type"] == "single_group"
    assert e["groups"][0]["num_participants"] == 4


def test_empty_bracket_large_is_single_elim():
    e = build_empty_bracket(12)
    assert e["type"] == "single_elim"
    assert e["bracket_size"] == 16


def test_round_robin_table_shows_opponents():
    b = build_initial_bracket(_people(4))
    rows = b["groups"][0]["rows"]
    # 4 wrestlers -> 3 rounds, no byes; pairings are reciprocal
    assert all(len(r["cells"]) == 3 for r in rows)
    assert all(r["rest_round"] is None for r in rows)  # even count: nobody rests
    # row 1 faces row X in round k  <=>  row X faces row 1 in round k
    for r_idx, opp in enumerate(rows[0]["cells"]):
        assert rows[opp - 1]["cells"][r_idx] == 1


def test_round_robin_odd_marks_bye_in_cells():
    b = build_initial_bracket(_people(5))
    rows = b["groups"][0]["rows"]
    # one None (bye) per wrestler somewhere in their schedule
    assert all(r["cells"].count(None) == 1 for r in rows)
    assert all(r["rest_round"] is not None for r in rows)


def test_empty_bracket_has_no_prefilled_numbers():
    e = build_empty_bracket(4)
    assert e["editable"] is True
    rows = e["groups"][0]["rows"]
    # names blank, numbers not pre-assigned (referee fills them in)
    assert all(r["name"] == "" and r["number"] is None for r in rows)

    se = build_empty_bracket(12)
    assert se["editable"] is True
    first = se["rounds"][0]["matches"]
    assert all(m["top"] is None and m["bottom"] is None for m in first)
