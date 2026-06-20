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
