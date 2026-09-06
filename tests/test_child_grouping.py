from dataclasses import dataclass
from decimal import Decimal

from app.services.child_grouping import group_children


@dataclass
class Child:
    name: str
    actual_weight: Decimal | None


def _children(count: int):
    return [Child(f"D{i}", Decimal("20") + Decimal(i) / 10) for i in range(count)]


def test_preferred_group_sizes_avoid_single_leftovers():
    assert [len(g.members) for g in group_children(_children(8))] == [4, 4]
    assert [len(g.members) for g in group_children(_children(9))] == [4, 5]
    assert [len(g.members) for g in group_children(_children(10))] == [5, 5]
    assert [len(g.members) for g in group_children(_children(11))] == [4, 4, 3]


def test_groups_are_weight_adjacent_and_review_wide_or_small_groups():
    children = [
        Child("heavy", Decimal("30")),
        Child("light", Decimal("20")),
        Child("b", Decimal("20.5")),
        Child("c", Decimal("21")),
    ]
    group = group_children(children)[0]
    assert [c.name for c in group.members] == ["light", "b", "c", "heavy"]
    assert group.needs_review is True  # spread is above the soft 3 kg limit


def test_missing_weight_is_never_dropped():
    groups = group_children(_children(4) + [Child("unknown", None)])
    assert len(groups) == 2
    assert groups[-1].members[0].name == "unknown"
    assert groups[-1].needs_review is True
