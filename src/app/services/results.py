"""Persist fights, advance winners, and calculate tournament standings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bout, Participant, Round
from app.services.brackets import round_robin_rounds
from app.services.child_grouping import is_children_category


@dataclass(frozen=True)
class BoutDefinition:
    key: str
    stage: str
    group_name: str | None
    sequence: int
    player_a_id: int | None = None
    player_b_id: int | None = None
    source_a: str | None = None
    source_b: str | None = None


def sync_bouts(db: Session, rnd: Round) -> None:
    """Synchronise mutable Bout rows with the immutable bracket layout."""
    definitions = _definitions(rnd.data or {})
    existing = {
        bout.key: bout
        for bout in db.scalars(select(Bout).where(Bout.round_id == rnd.id)).all()
    }
    wanted = {definition.key for definition in definitions}
    valid_tiebreak_groups = {
        group.get("name") or "S": {
            row.get("participant_id")
            for row in group.get("rows") or []
            if row.get("participant_id") is not None
        }
        for group in (rnd.data or {}).get("groups") or []
        if group.get("type") == "round_robin"
    }
    for bout in existing.values():
        tiebreak_players = {bout.player_a_id, bout.player_b_id} - {None}
        valid_tiebreak = (
            bout.stage == "tiebreak"
            and bout.group_name in valid_tiebreak_groups
            and len(tiebreak_players) == 2
            and tiebreak_players <= valid_tiebreak_groups[bout.group_name]
        )
        if bout.key not in wanted and not valid_tiebreak:
            db.delete(bout)

    for definition in definitions:
        bout = existing.get(definition.key)
        if bout is None:
            bout = Bout(round_id=rnd.id, key=definition.key)
            db.add(bout)
        bout.stage = definition.stage
        bout.group_name = definition.group_name
        bout.sequence = definition.sequence
        bout.source_a = definition.source_a
        bout.source_b = definition.source_b
        if definition.source_a is None:
            bout.player_a_id = definition.player_a_id
        if definition.source_b is None:
            bout.player_b_id = definition.player_b_id
    db.flush()
    recalculate(db, rnd)


def recalculate(db: Session, rnd: Round) -> dict[str, Any]:
    """Advance resolved sources and return the current public result state."""
    bouts = list(
        db.scalars(
            select(Bout)
            .where(Bout.round_id == rnd.id)
            .order_by(Bout.sequence, Bout.id)
        ).all()
    )
    by_key = {bout.key: bout for bout in bouts}

    # Knockout dependencies may cascade through multiple rounds.
    for _ in range(len(bouts) + 1):
        changed = False
        for bout in bouts:
            if bout.source_a and bout.source_a.startswith("bout:"):
                changed |= _assign_player(bout, "a", _winner(by_key, bout.source_a[5:]))
            if bout.source_b and bout.source_b.startswith("bout:"):
                changed |= _assign_player(bout, "b", _winner(by_key, bout.source_b[5:]))
            changed |= _validate_or_advance_bye(bout)
        if not changed:
            break

    groups = _group_standings(rnd.data or {}, bouts)
    group_map = {group["name"]: group for group in groups}

    for bout in bouts:
        if bout.source_a and not bout.source_a.startswith("bout:"):
            changed_id = _ranking_source(group_map, bout.source_a)
            _assign_player(bout, "a", changed_id)
        if bout.source_b and not bout.source_b.startswith("bout:"):
            changed_id = _ranking_source(group_map, bout.source_b)
            _assign_player(bout, "b", changed_id)
        _validate_or_advance_bye(bout)

    # Finalists become known only after both semifinals are decided.
    for _ in range(3):
        for bout in bouts:
            if bout.source_a and bout.source_a.startswith("bout:"):
                _assign_player(bout, "a", _winner(by_key, bout.source_a[5:]))
            if bout.source_b and bout.source_b.startswith("bout:"):
                _assign_player(bout, "b", _winner(by_key, bout.source_b[5:]))
            _validate_or_advance_bye(bout)

    standings = _overall_standings(
        rnd.data or {},
        groups,
        by_key,
        children=is_children_category(rnd.weight_category.age_category.name),
    )
    participants = _participants_by_id(db, bouts, standings)
    public_groups = [
        {
            **group,
            "ranking": [
                {**row, "name": participants.get(row["participant_id"], "—")}
                for row in group["ranking"]
            ],
            "ties": [
                {
                    **tie,
                    "participants": [
                        {
                            "id": participant_id,
                            "name": participants.get(participant_id, "—"),
                        }
                        for participant_id in tie["participant_ids"]
                    ],
                }
                for tie in group.get("ties", [])
            ],
        }
        for group in groups
    ]
    ties = [tie for group in public_groups for tie in group.get("ties", [])]
    db.flush()
    return {
        "groups": public_groups,
        "ties": ties,
        "standings": [
            {**row, "name": participants.get(row["participant_id"], "—")}
            for row in standings
        ],
        "complete": bool(standings),
        "bouts": [_bout_payload(bout, participants) for bout in bouts],
    }


def set_winner(db: Session, bout: Bout, winner_id: int | None) -> None:
    """Set or clear a winner, rejecting a wrestler outside the bout."""
    allowed = {bout.player_a_id, bout.player_b_id} - {None}
    if winner_id is not None and winner_id not in allowed:
        raise ValueError("Zwycięzca nie uczestniczy w tej walce")
    bout.winner_id = winner_id
    bout.status = "complete" if winner_id is not None else "pending"
    db.flush()


def create_tiebreak(
    db: Session,
    rnd: Round,
    group_name: str,
    participant_ids: list[int],
) -> list[Bout]:
    """Create one round-robin replay for an unresolved cyclic tie."""
    participant_ids = list(dict.fromkeys(participant_ids))
    state = recalculate(db, rnd)
    requested = set(participant_ids)
    allowed = next(
        (
            tie
            for tie in state.get("ties", [])
            if tie["group_name"] == group_name
            and tie["status"] == "needed"
            and set(tie["participant_ids"]) == requested
        ),
        None,
    )
    if allowed is None:
        raise ValueError("Ta dogrywka nie jest już potrzebna lub lista zawodników się zmieniła")
    if not 3 <= len(participant_ids) <= 5:
        raise ValueError("Dogrywka kołowa wymaga od 3 do 5 zawodników")

    existing = list(
        db.scalars(
            select(Bout)
            .where(Bout.round_id == rnd.id)
            .order_by(Bout.sequence, Bout.id)
        )
    )
    series = max(
        (
            parsed[0]
            for bout in existing
            if bout.group_name == group_name
            and (parsed := _tiebreak_key(bout.key)) is not None
        ),
        default=0,
    ) + 1
    sequence = max((bout.sequence for bout in existing), default=0)
    created: list[Bout] = []
    pair_number = 0
    for pairs in round_robin_rounds(len(participant_ids)):
        for a, b in pairs:
            if a is None or b is None:
                continue
            pair_number += 1
            sequence += 1
            bout = Bout(
                round_id=rnd.id,
                key=f"G{group_name}-TB-{series}-{pair_number}",
                stage="tiebreak",
                group_name=group_name,
                sequence=sequence,
                player_a_id=participant_ids[a - 1],
                player_b_id=participant_ids[b - 1],
            )
            db.add(bout)
            created.append(bout)
    db.flush()
    return created


def _definitions(data: dict[str, Any]) -> list[BoutDefinition]:
    definitions: list[BoutDefinition] = []
    groups = data.get("groups") or ([] if data.get("type") != "single_elim" else [data])
    for group in groups:
        label = group.get("name") or "S"
        rows = {row.get("lp"): row.get("participant_id") for row in group.get("rows") or []}
        if group.get("type") == "round_robin":
            for item in group.get("bouts") or []:
                definitions.append(
                    BoutDefinition(
                        key=f"G{label}-RR-{item['sequence']}",
                        stage="group",
                        group_name=label,
                        sequence=len(definitions) + 1,
                        player_a_id=rows.get(item.get("a")),
                        player_b_id=rows.get(item.get("b")),
                    )
                )
        elif group.get("type") == "single_elim":
            definitions.extend(_knockout_definitions(group, label, rows, len(definitions)))

    if data.get("final"):
        definitions.extend(
            [
                BoutDefinition("FINAL-SF1", "semifinal", None, len(definitions) + 1, source_a="A1", source_b="B2"),
                BoutDefinition("FINAL-SF2", "semifinal", None, len(definitions) + 2, source_a="B1", source_b="A2"),
                BoutDefinition(
                    "FINAL-GOLD",
                    "final",
                    None,
                    len(definitions) + 3,
                    source_a="bout:FINAL-SF1",
                    source_b="bout:FINAL-SF2",
                ),
            ]
        )
    return definitions


def _knockout_definitions(
    group: dict[str, Any], label: str, rows: dict[int, int | None], offset: int
) -> list[BoutDefinition]:
    result: list[BoutDefinition] = []
    for round_pos, round_data in enumerate(group.get("rounds") or [], start=1):
        for match_pos, match in enumerate(round_data.get("matches") or [], start=1):
            key = f"G{label}-KO-R{round_pos}-M{match_pos}"
            kwargs: dict[str, Any] = {}
            if round_pos == 1:
                kwargs["player_a_id"] = rows.get(match.get("top"))
                kwargs["player_b_id"] = rows.get(match.get("bottom"))
            else:
                kwargs["source_a"] = f"bout:G{label}-KO-R{round_pos - 1}-M{match_pos * 2 - 1}"
                kwargs["source_b"] = f"bout:G{label}-KO-R{round_pos - 1}-M{match_pos * 2}"
            result.append(
                BoutDefinition(
                    key=key,
                    stage="group_knockout",
                    group_name=label,
                    sequence=offset + len(result) + 1,
                    **kwargs,
                )
            )
    return result


def _assign_player(bout: Bout, side: str, participant_id: int | None) -> bool:
    attr = f"player_{side}_id"
    if getattr(bout, attr) == participant_id:
        return False
    setattr(bout, attr, participant_id)
    if bout.winner_id not in {bout.player_a_id, bout.player_b_id}:
        bout.winner_id = None
        bout.status = "pending"
    return True


def _validate_or_advance_bye(bout: Bout) -> bool:
    players = [pid for pid in (bout.player_a_id, bout.player_b_id) if pid is not None]
    if bout.winner_id is not None and bout.winner_id not in players:
        bout.winner_id = None
        bout.status = "pending"
        return True
    if bout.stage == "group_knockout" and len(players) == 1 and bout.winner_id != players[0]:
        bout.winner_id = players[0]
        bout.status = "automatic"
        return True
    return False


def _winner(by_key: dict[str, Bout], key: str) -> int | None:
    bout = by_key.get(key)
    return bout.winner_id if bout else None


def _group_standings(data: dict[str, Any], bouts: list[Bout]) -> list[dict[str, Any]]:
    result = []
    for group in data.get("groups") or []:
        label = group.get("name") or "S"
        group_bouts = [bout for bout in bouts if bout.group_name == label]
        rows = group.get("rows") or []
        if group.get("type") == "round_robin":
            base_bouts = [bout for bout in group_bouts if bout.stage == "group"]
            tiebreak_bouts = [bout for bout in group_bouts if bout.stage == "tiebreak"]
            complete = (len(rows) <= 1) or (
                bool(base_bouts) and all(bout.winner_id for bout in base_bouts)
            )
            wins = {row.get("participant_id"): 0 for row in rows if row.get("participant_id")}
            for bout in base_bouts:
                if bout.winner_id in wins:
                    wins[bout.winner_id] += 1
            ordered = sorted(
                [row for row in rows if row.get("participant_id")],
                key=lambda row: (-wins[row["participant_id"]], row.get("lp") or 9999),
            )
            ties: list[dict[str, Any]] = []
            if complete:
                ordered, ties = _resolve_equal_wins(
                    ordered,
                    wins,
                    base_bouts,
                    tiebreak_bouts,
                    label,
                )
                complete = not ties
            unresolved_ids = {
                participant_id
                for tie in ties
                for participant_id in tie["participant_ids"]
            }
            ranking = [
                {
                    "participant_id": row["participant_id"],
                    "wins": wins[row["participant_id"]],
                    "place": (
                        None if row["participant_id"] in unresolved_ids else pos
                    ),
                }
                for pos, row in enumerate(ordered, start=1)
            ]
        else:
            final_bout = group_bouts[-1] if group_bouts else None
            complete = bool(final_bout and final_bout.winner_id and final_bout.player_a_id and final_bout.player_b_id)
            ranking = []
            if complete:
                loser = final_bout.player_b_id if final_bout.winner_id == final_bout.player_a_id else final_bout.player_a_id
                ranking = [
                    {"participant_id": final_bout.winner_id, "wins": None, "place": 1},
                    {"participant_id": loser, "wins": None, "place": 2},
                ]
            ties = []
        result.append(
            {"name": label, "complete": complete, "ranking": ranking, "ties": ties}
        )
    return result


def _resolve_equal_wins(
    rows: list[dict],
    wins: dict[int, int],
    base_bouts: list[Bout],
    tiebreak_bouts: list[Bout],
    group_name: str,
) -> tuple[list[dict], list[dict[str, Any]]]:
    result: list[dict] = []
    ties: list[dict[str, Any]] = []
    start = 0
    while start < len(rows):
        end = start + 1
        while (
            end < len(rows)
            and wins[rows[end]["participant_id"]] == wins[rows[start]["participant_id"]]
        ):
            end += 1
        bucket = rows[start:end]
        if len(bucket) == 2:
            bucket = _head_to_head(bucket, base_bouts)
        elif len(bucket) >= 3:
            bucket, unresolved = _resolve_tiebreak_bucket(
                bucket, tiebreak_bouts, group_name
            )
            ties.extend(unresolved)
        result.extend(bucket)
        start = end
    return result, ties


def _resolve_tiebreak_bucket(
    rows: list[dict],
    bouts: list[Bout],
    group_name: str,
    *,
    after_series: int = 0,
) -> tuple[list[dict], list[dict[str, Any]]]:
    participant_ids = [row["participant_id"] for row in rows]
    requested = set(participant_ids)
    series = _tiebreak_series(bouts)
    matching = [
        (number, series_bouts)
        for number, series_bouts in sorted(series.items())
        if number > after_series
        and {
            pid
            for bout in series_bouts
            for pid in (bout.player_a_id, bout.player_b_id)
            if pid is not None
        }
        == requested
    ]
    if not matching:
        return rows, [_tie_state(group_name, participant_ids, "needed")]

    series_number, series_bouts = matching[-1]
    if not all(bout.winner_id for bout in series_bouts):
        return rows, [
            _tie_state(group_name, participant_ids, "in_progress", series_number)
        ]

    series_wins = {participant_id: 0 for participant_id in participant_ids}
    for bout in series_bouts:
        if bout.winner_id in series_wins:
            series_wins[bout.winner_id] += 1
    ordered = sorted(
        rows,
        key=lambda row: (
            -series_wins[row["participant_id"]],
            participant_ids.index(row["participant_id"]),
        ),
    )
    result: list[dict] = []
    ties: list[dict[str, Any]] = []
    start = 0
    while start < len(ordered):
        end = start + 1
        while (
            end < len(ordered)
            and series_wins[ordered[end]["participant_id"]]
            == series_wins[ordered[start]["participant_id"]]
        ):
            end += 1
        bucket = ordered[start:end]
        if len(bucket) == 2:
            bucket = _head_to_head(bucket, series_bouts)
        elif len(bucket) >= 3:
            bucket, unresolved = _resolve_tiebreak_bucket(
                bucket,
                bouts,
                group_name,
                after_series=series_number,
            )
            ties.extend(unresolved)
        result.extend(bucket)
        start = end
    return result, ties


def _head_to_head(rows: list[dict], bouts: list[Bout]) -> list[dict]:
    first, second = rows
    duel = next(
        (
            bout
            for bout in bouts
            if {bout.player_a_id, bout.player_b_id}
            == {first["participant_id"], second["participant_id"]}
        ),
        None,
    )
    if duel and duel.winner_id == second["participant_id"]:
        return [second, first]
    return rows


def _tiebreak_key(key: str) -> tuple[int, int] | None:
    parts = key.rsplit("-TB-", 1)
    if len(parts) != 2:
        return None
    numbers = parts[1].split("-")
    if len(numbers) != 2 or not all(number.isdigit() for number in numbers):
        return None
    return int(numbers[0]), int(numbers[1])


def _tiebreak_series(bouts: list[Bout]) -> dict[int, list[Bout]]:
    result: dict[int, list[Bout]] = {}
    for bout in bouts:
        parsed = _tiebreak_key(bout.key)
        if parsed is not None:
            result.setdefault(parsed[0], []).append(bout)
    return result


def _tie_state(
    group_name: str,
    participant_ids: list[int],
    status: str,
    series: int | None = None,
) -> dict[str, Any]:
    return {
        "group_name": group_name,
        "participant_ids": participant_ids,
        "status": status,
        "series": series,
    }


def _ranking_source(groups: dict[str, dict], source: str) -> int | None:
    if len(source) < 2 or not source[1:].isdigit():
        return None
    group = groups.get(source[0])
    place = int(source[1:])
    if not group or not group["complete"] or len(group["ranking"]) < place:
        return None
    return group["ranking"][place - 1]["participant_id"]


def _overall_standings(
    data: dict[str, Any],
    groups: list[dict],
    by_key: dict[str, Bout],
    *,
    children: bool = False,
) -> list[dict[str, int]]:
    if data.get("final"):
        gold = by_key.get("FINAL-GOLD")
        sf1, sf2 = by_key.get("FINAL-SF1"), by_key.get("FINAL-SF2")
        if not gold or not gold.winner_id or not sf1 or not sf2:
            return []
        silver = gold.player_b_id if gold.winner_id == gold.player_a_id else gold.player_a_id
        bronze = []
        for semifinal in (sf1, sf2):
            if not semifinal.winner_id:
                return []
            loser = semifinal.player_b_id if semifinal.winner_id == semifinal.player_a_id else semifinal.player_a_id
            if loser is not None:
                bronze.append(loser)
        return [
            {"participant_id": gold.winner_id, "place": 1},
            {"participant_id": silver, "place": 2},
            *[{"participant_id": pid, "place": 3} for pid in bronze],
        ]
    if len(groups) == 1 and groups[0]["complete"]:
        return [
            {
                "participant_id": row["participant_id"],
                "place": 3 if children and row["place"] >= 3 else row["place"],
            }
            for row in groups[0]["ranking"]
        ]
    return []


def _participants_by_id(db: Session, bouts: list[Bout], standings: list[dict]) -> dict[int, str]:
    ids = {
        pid
        for bout in bouts
        for pid in (bout.player_a_id, bout.player_b_id, bout.winner_id)
        if pid is not None
    }
    ids.update(row["participant_id"] for row in standings if row.get("participant_id"))
    if not ids:
        return {}
    return {p.id: p.name for p in db.scalars(select(Participant).where(Participant.id.in_(ids))).all()}


def _bout_payload(bout: Bout, participants: dict[int, str]) -> dict[str, Any]:
    return {
        "id": bout.id,
        "key": bout.key,
        "stage": bout.stage,
        "group_name": bout.group_name,
        "sequence": bout.sequence,
        "player_a_id": bout.player_a_id,
        "player_b_id": bout.player_b_id,
        "player_a": participants.get(bout.player_a_id, "—"),
        "player_b": participants.get(bout.player_b_id, "—"),
        "winner_id": bout.winner_id,
        "status": bout.status,
        "ready": bout.player_a_id is not None and bout.player_b_id is not None,
    }
