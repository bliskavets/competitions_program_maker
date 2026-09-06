"""Grouping rules for the youngest (``Dzieci``) age categories.

The customer treats roughly three kilograms as a review threshold rather than
an absolute boundary.  We therefore keep neighbouring weights together,
prefer four-person groups, allow five, and explicitly flag unavoidable smaller
or unusually wide groups for a human decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterable


TARGET_SIZE = 4
MAX_SIZE = 5
SOFT_MAX_SPREAD = Decimal("3.00")


@dataclass(frozen=True)
class ChildGroup:
    members: list[Any]
    index: int
    min_weight: Decimal | None
    max_weight: Decimal | None
    needs_review: bool

    @property
    def representative_weight(self) -> float | None:
        weights = [self.min_weight, self.max_weight]
        if any(w is None for w in weights):
            return None
        return float((weights[0] + weights[1]) / 2)

    @property
    def name(self) -> str:
        if self.min_weight is None or self.max_weight is None:
            return f"Grupa {self.index} · do weryfikacji"
        lo = _fmt(self.min_weight)
        hi = _fmt(self.max_weight)
        weight_range = f"{lo} kg" if lo == hi else f"{lo}–{hi} kg"
        return f"Grupa {self.index} · {weight_range}"


def is_children_category(name: str | None) -> bool:
    normalized = (name or "").strip().casefold()
    return "dzieci" in normalized or "child" in normalized


def group_children(
    participants: Iterable[Any],
    *,
    weight_of: Callable[[Any], Decimal | None] = lambda p: p.actual_weight,
    soft_max_spread: Decimal = SOFT_MAX_SPREAD,
) -> list[ChildGroup]:
    """Return stable, weight-adjacent groups and review flags.

    Known weights are sorted ascending. Missing/invalid weights are kept in a
    final review group so no imported participant disappears.
    """
    known: list[tuple[Decimal, Any]] = []
    unknown: list[Any] = []
    for participant in participants:
        weight = weight_of(participant)
        if weight is None:
            unknown.append(participant)
        else:
            known.append((Decimal(weight), participant))
    known.sort(key=lambda item: item[0])

    sizes = _preferred_sizes(len(known))
    result: list[ChildGroup] = []
    offset = 0
    group_index = 1
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
                needs_review=(len(chunk) < TARGET_SIZE or len(chunk) > MAX_SIZE or hi - lo > soft_max_spread),
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
            )
        )
    return result


def _preferred_sizes(count: int) -> list[int]:
    """Choose 4/5-person groups while avoiding one-person leftovers.

    A three-person review group is preferred over a pair, and a pair over a
    singleton. This matches the operational goal: minimise manual rescue work
    without silently creating groups larger than five.
    """
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
        return [MAX_SIZE] * (count // MAX_SIZE) + ([count % MAX_SIZE] if count % MAX_SIZE else [])
    return min(candidates, key=lambda item: item[0])[1]


def _fmt(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.01"))
    text = format(normalized, "f").rstrip("0").rstrip(".")
    return text.replace(".", ",")
