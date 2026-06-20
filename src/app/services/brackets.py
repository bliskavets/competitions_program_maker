"""Tournament bracket / round-robin generation.

Mirrors the printed "krzyżówki SUMO" sheets:

* Groups of <= 5 wrestlers fight round-robin ("każdy z każdym").  The schedule
  is produced with the standard circle method (Berger table); when the number
  of wrestlers is odd, one of them rests each round and that cell is marked
  ``wl`` (wolny los) on the sheet.
* Larger fields are split into two halves — Grupa A and Grupa B.  Each half is
  run on its own (round-robin if it has <= 5 wrestlers, otherwise a single
  elimination bracket).  The top two of each group cross over in the FINAŁ
  block (A1–B2, B1–A2), which yields places 1, 2 and two bronze (3, 3) — the
  repechage for third place.

The functions here are pure: they take counts / participant dicts and return
plain JSON-serialisable structures so they can be stored on ``Round.data`` and
rendered by templates, Excel and PDF exporters alike.
"""
from __future__ import annotations

from typing import Any

ROUND_ROBIN_MAX = 5  # groups with <= this many wrestlers use round-robin


def round_robin_rounds(n: int) -> list[list[tuple[int | None, int | None]]]:
    """Return the round-robin schedule for ``n`` wrestlers (1-based numbers).

    Each element is one round: a list of ``(a, b)`` pairs.  ``None`` means a
    bye — the opposing wrestler rests that round.  Uses the circle method, so
    every wrestler meets every other exactly once.
    """
    if n <= 1:
        return []
    players: list[int | None] = list(range(1, n + 1))
    if n % 2 == 1:
        players.append(None)  # odd → phantom opponent = bye
    m = len(players)
    arr = players[:]
    rounds: list[list[tuple[int | None, int | None]]] = []
    for _ in range(m - 1):
        pairs: list[tuple[int | None, int | None]] = []
        for i in range(m // 2):
            a, b = arr[i], arr[m - 1 - i]
            pairs.append((a, b))
        rounds.append(pairs)
        # rotate everyone except the first element
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    return rounds


def rest_rounds(n: int) -> dict[int, int]:
    """Map wrestler number -> the round index (1-based) in which they rest."""
    rests: dict[int, int] = {}
    for r_idx, pairs in enumerate(round_robin_rounds(n), start=1):
        for a, b in pairs:
            if a is None and b is not None:
                rests[b] = r_idx
            elif b is None and a is not None:
                rests[a] = r_idx
    return rests


def round_robin_table(participants: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a round-robin sheet structure for a single group.

    ``participants`` is a list of dicts (number, name, year, team, other...).
    For every wrestler (row) and every round (column) the table records the
    *opponent's* position (``cells``), or ``None`` when the wrestler rests that
    round (rendered as ``wl``). This mirrors the "Kategoria wagowa" pairing grid
    of the printed sheet, where you can read who fights whom in each round.
    """
    n = len(participants)
    schedule = round_robin_rounds(n)
    num_rounds = len(schedule)

    # opponent[position][round_index] = opponent position (1-based) or None (bye)
    opponent: dict[int, list[int | None]] = {
        i: [None] * num_rounds for i in range(1, n + 1)
    }
    for r_idx, pairs in enumerate(schedule):
        for a, b in pairs:
            if a is not None and b is not None:
                opponent[a][r_idx] = b
                opponent[b][r_idx] = a

    rows = []
    for idx, p in enumerate(participants, start=1):
        cells = opponent[idx]
        rest = next((r + 1 for r, o in enumerate(cells) if o is None), None)
        rows.append(
            {
                "lp": idx,
                "number": p.get("number"),
                "name": p.get("name", ""),
                "year": p.get("year") or p.get("birth_year"),
                "team": p.get("team"),
                "other": p.get("other") or p.get("other_info"),
                "cells": cells,  # opponent position per round (None = bye/wl)
                "rest_round": rest,
            }
        )
    # schedule as list of rounds, each a list of {a,b} (positions, None=bye)
    sched_json = [[{"a": a, "b": b} for (a, b) in rnd] for rnd in schedule]
    return {
        "type": "round_robin",
        "num_participants": n,
        "num_rounds": num_rounds,
        "rows": rows,
        "schedule": sched_json,
    }


def single_elimination(n: int, blank: bool = False) -> dict[str, Any]:
    """Build a single-elimination bracket for ``n`` wrestlers.

    Wrestlers are seeded into the next power-of-two sized bracket; the surplus
    slots become byes so that some wrestlers rest in the first round (marked
    "wolny / свободен" and greyed out in the UI).

    When ``blank`` is True the first-round slots are left empty (no positions
    pre-filled) — used for rounds 2+, where the referee enters the draw numbers
    of the wrestlers who advanced.
    """
    if n < 1:
        return {"type": "single_elim", "num_participants": 0, "rounds": []}
    size = 1
    while size < n:
        size *= 2
    byes = size - n

    # Round 1 slots: standard seeding order so byes are spread out.
    seeds = _seed_order(size)
    # Map slot -> wrestler position (1..n) or None for a bye.
    slot_to_player: dict[int, int | None] = {}
    player = 1
    for slot in seeds:
        if blank:
            slot_to_player[slot] = None
        elif slot <= n:
            slot_to_player[slot] = player
            player += 1
        else:
            slot_to_player[slot] = None

    rounds: list[dict[str, Any]] = []
    # First round matches
    matches = []
    ordered_slots = seeds
    for i in range(0, size, 2):
        top = slot_to_player.get(ordered_slots[i])
        bottom = slot_to_player.get(ordered_slots[i + 1])
        matches.append({"top": top, "bottom": bottom})
    rounds.append({"round": 1, "matches": matches})

    # Subsequent rounds are empty (winners advance during the event)
    current = size // 2
    r = 2
    while current > 1:
        rounds.append(
            {
                "round": r,
                "matches": [{"top": None, "bottom": None} for _ in range(current // 2)],
            }
        )
        current //= 2
        r += 1
    return {
        "type": "single_elim",
        "num_participants": n,
        "bracket_size": size,
        "byes": byes,
        "rounds": rounds,
    }


def _seed_order(size: int) -> list[int]:
    """Standard tournament seeding order for a bracket of ``size`` slots."""
    order = [1]
    while len(order) < size:
        new: list[int] = []
        rounds_count = len(order) * 2 + 1
        for s in order:
            new.append(s)
            new.append(rounds_count - s)
        order = new
    return order


def build_initial_bracket(participants: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the Round-1 structure for a whole weight category.

    * <= 5 wrestlers: single round-robin group.
    * otherwise: split into Grupa A / Grupa B, each round-robin or bracket,
      with a FINAŁ crossover (A1–B2, B1–A2) and places 1, 2, 3, 3.
    """
    n = len(participants)
    if n <= ROUND_ROBIN_MAX:
        return {
            "type": "single_group",
            "num_participants": n,
            "groups": [{"name": "", **round_robin_table(participants)}],
            "final": None,
        }

    half = (n + 1) // 2
    halves = [("A", participants[:half]), ("B", participants[half:])]
    groups = []
    for name, members in halves:
        if len(members) <= ROUND_ROBIN_MAX:
            groups.append({"name": name, **round_robin_table(members)})
        else:
            groups.append(
                {
                    "name": name,
                    **single_elimination(len(members)),
                    "rows": [
                        {
                            "lp": i + 1,
                            "name": p.get("name", ""),
                            "year": p.get("year") or p.get("birth_year"),
                            "team": p.get("team"),
                        }
                        for i, p in enumerate(members)
                    ],
                }
            )
    final = {
        "pairs": [["A1", "B2"], ["B1", "A2"]],
        "places": [1, 2, 3, 3],  # two bronze via repechage
    }
    return {
        "type": "groups",
        "num_participants": n,
        "groups": groups,
        "final": final,
    }


def build_empty_bracket(n: int) -> dict[str, Any]:
    """Empty bracket for Round 2+ given a user-entered participant count.

    Rows/slots carry NO pre-filled numbers — the referee enters the draw numbers
    of the wrestlers (and uses "Fillup" to pull their names). Only the pairing
    structure (who-fights-whom by position) and the byes are pre-computed.
    """
    if n <= ROUND_ROBIN_MAX:
        # Round-robin pairing grid with empty rows (no names/numbers yet).
        placeholders = [{"name": "", "year": None, "team": None} for _ in range(n)]
        table = round_robin_table(placeholders)
        for row in table["rows"]:
            row["editable"] = True  # render a Number input + fillable name
        return {
            "type": "single_group",
            "num_participants": n,
            "editable": True,
            "groups": [{"name": "", **table}],
            "final": None,
        }
    se = single_elimination(n, blank=True)
    se["editable"] = True
    return se
