"""Grouping rules for the youngest (``Dzieci``) age categories.

Children are first separated by gender and fixed three-year age bands, then
grouped by neighbouring weights. The weight spread is a review threshold
rather than an absolute boundary: prefer four-person groups, allow five, and
flag unavoidable smaller or unusually wide groups for a human decision.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

TARGET_SIZE = 4
MAX_SIZE = 5
SOFT_MAX_SPREAD = Decimal("3.00")
MIN_AGE = 3
AGE_BAND_YEARS = 3

FEMALE = "female"
MALE = "male"


@dataclass(frozen=True)
class ChildGroup:
    members: list[Any]
    index: int
    min_weight: Decimal | None
    max_weight: Decimal | None
    needs_review: bool
    gender: str | None = None
    min_age: int | None = None
    max_age: int | None = None

    @property
    def representative_weight(self) -> float | None:
        weights = [self.min_weight, self.max_weight]
        if any(weight is None for weight in weights):
            return None
        return float((weights[0] + weights[1]) / 2)

    @property
    def name(self) -> str:
        gender_label = {
            FEMALE: "Dziewczęta",
            MALE: "Chłopcy",
        }.get(self.gender, "Płeć do weryfikacji")
        age_label = (
            f"{self.min_age}–{self.max_age} lat"
            if self.min_age is not None and self.max_age is not None
            else "wiek do weryfikacji"
        )
        if self.min_weight is None or self.max_weight is None:
            return (
                f"{gender_label} · {age_label} · Grupa {self.index} · "
                "waga do weryfikacji"
            )
        lo = _fmt(self.min_weight)
        hi = _fmt(self.max_weight)
        weight_range = f"{lo} kg" if lo == hi else f"{lo}–{hi} kg"
        return f"{gender_label} · {age_label} · Grupa {self.index} · {weight_range}"


def is_children_category(name: str | None) -> bool:
    normalized = (name or "").strip().casefold()
    return "dzieci" in normalized or "child" in normalized


def normalize_gender(value: Any) -> str | None:
    """Return the canonical imported gender value used by grouping and forms."""
    if value is None:
        return None
    token = unicodedata.normalize("NFKD", str(value).strip().casefold())
    token = "".join(char for char in token if not unicodedata.combining(char))
    token = token.replace("ł", "l")
    token = " ".join(token.split())
    if token in {
        "f",
        "female",
        "girl",
        "k",
        "kobieta",
        "dziewczyna",
        "dziewczynka",
        "dziewczeta",
        "kobiety",
        "zenska",
    }:
        return FEMALE
    if token in {
        "m",
        "male",
        "boy",
        "mezczyzna",
        "chlopak",
        "chlopiec",
        "chlopcy",
        "mezczyzni",
        "meska",
    }:
        return MALE
    return None


def group_children(
    participants: Iterable[Any],
    *,
    weight_of: Callable[[Any], Decimal | None] = lambda p: p.actual_weight,
    birth_year_of: Callable[[Any], int | None] = lambda p: getattr(p, "year", None)
    or getattr(p, "birth_year", None),
    gender_of: Callable[[Any], str | None] = lambda p: getattr(p, "gender", None),
    reference_year: int | None = None,
    soft_max_spread: Decimal = SOFT_MAX_SPREAD,
) -> list[ChildGroup]:
    """Return stable groups split by gender, three-year bands and weight.

    Age bands are fixed at 3–5, 6–8, 9–11, ... using the competition year.
    Missing or invalid demographic data is kept in an explicit review group,
    so no participant is silently dropped or guessed from their name.
    """
    reference_year = reference_year or date.today().year
    partitions: dict[tuple[str | None, int | None, int | None], list[Any]] = {}
    for participant in participants:
        gender = normalize_gender(gender_of(participant))
        min_age, max_age = _age_band(birth_year_of(participant), reference_year)
        partitions.setdefault((gender, min_age, max_age), []).append(participant)

    result: list[ChildGroup] = []
    group_index = 1
    ordered_partitions = sorted(
        partitions.items(), key=lambda item: _partition_sort_key(item[0])
    )
    for (gender, min_age, max_age), members in ordered_partitions:
        known: list[tuple[Decimal, Any]] = []
        unknown: list[Any] = []
        for participant in members:
            weight = weight_of(participant)
            if weight is None:
                unknown.append(participant)
            else:
                known.append((Decimal(str(weight)), participant))
        known.sort(key=lambda item: item[0])

        sizes = _preferred_sizes(len(known))
        offset = 0
        demographic_review = gender is None or min_age is None
        for size in sizes:
            chunk = known[offset : offset + size]
            offset += size
            if not chunk:
                continue
            lo, hi = chunk[0][0], chunk[-1][0]
            result.append(
                ChildGroup(
                    members=[item[1] for item in chunk],
                    index=group_index,
                    min_weight=lo,
                    max_weight=hi,
                    needs_review=(
                        demographic_review
                        or len(chunk) < TARGET_SIZE
                        or len(chunk) > MAX_SIZE
                        or hi - lo > soft_max_spread
                    ),
                    gender=gender,
                    min_age=min_age,
                    max_age=max_age,
                )
            )
            group_index += 1
        if unknown:
            result.append(
                ChildGroup(
                    members=unknown,
                    index=group_index,
                    min_weight=None,
                    max_weight=None,
                    needs_review=True,
                    gender=gender,
                    min_age=min_age,
                    max_age=max_age,
                )
            )
            group_index += 1
    return result


def _age_band(birth_year: int | None, reference_year: int) -> tuple[int | None, int | None]:
    try:
        age = reference_year - int(birth_year) if birth_year is not None else None
    except (TypeError, ValueError):
        age = None
    if age is None or age < MIN_AGE:
        return None, None
    start = MIN_AGE + ((age - MIN_AGE) // AGE_BAND_YEARS) * AGE_BAND_YEARS
    return start, start + AGE_BAND_YEARS - 1


def _partition_sort_key(
    key: tuple[str | None, int | None, int | None],
) -> tuple[int, int, int]:
    gender, min_age, max_age = key
    gender_order = {FEMALE: 0, MALE: 1, None: 2}
    return (
        gender_order.get(gender, 2),
        min_age if min_age is not None else 999,
        max_age if max_age is not None else 999,
    )


def _preferred_sizes(count: int) -> list[int]:
    """Choose 4/5-person groups while avoiding one-person leftovers."""
    if count <= 0:
        return []
    if count <= MAX_SIZE:
        return [count]

    remainder_rank = {0: 0, 3: 1, 2: 2, 1: 3}
    candidates: list[tuple[tuple[int, int, int], list[int]]] = []
    for fours in range(count // TARGET_SIZE + 1):
        for fives in range(count // MAX_SIZE + 1):
            used = fours * TARGET_SIZE + fives * MAX_SIZE
            remainder = count - used
            if used == 0 or remainder < 0 or remainder > 3:
                continue
            sizes = [TARGET_SIZE] * fours + [MAX_SIZE] * fives
            if remainder:
                sizes.append(remainder)
            score = (remainder_rank[remainder], fives, len(sizes))
            candidates.append((score, sizes))
    if not candidates:
        return [MAX_SIZE] * (count // MAX_SIZE) + (
            [count % MAX_SIZE] if count % MAX_SIZE else []
        )
    return min(candidates, key=lambda item: item[0])[1]


def _fmt(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.01"))
    text = format(normalized, "f").rstrip("0").rstrip(".")
    return text.replace(".", ",")
