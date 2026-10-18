from dataclasses import dataclass
from decimal import Decimal

from app.services.child_grouping import group_children


@dataclass
class Child:
    name: str
    actual_weight: Decimal | None
    birth_year: int | None = 2020
    gender: str | None = "male"


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


def test_children_are_separated_by_gender_before_weight_grouping():
    children = [
        Child(f"D{i}", Decimal("20") + Decimal(i) / 10, gender="female")
        for i in range(4)
    ] + [
        Child(f"C{i}", Decimal("20") + Decimal(i) / 10, gender="male")
        for i in range(4)
    ]

    groups = group_children(children, reference_year=2026)

    assert [group.gender for group in groups] == ["female", "male"]
    assert [len(group.members) for group in groups] == [4, 4]
    assert groups[0].name.startswith("Dziewczęta · 6–8 lat")
    assert groups[1].name.startswith("Chłopcy · 6–8 lat")


def test_children_are_separated_into_fixed_three_year_age_bands():
    children = [
        Child("3 lata", Decimal("20"), birth_year=2023),
        Child("5 lat", Decimal("20.5"), birth_year=2021),
        Child("6 lat", Decimal("20.7"), birth_year=2020),
        Child("8 lat", Decimal("21"), birth_year=2018),
    ]

    groups = group_children(children, reference_year=2026)

    assert [[child.name for child in group.members] for group in groups] == [
        ["3 lata", "5 lat"],
        ["6 lat", "8 lat"],
    ]
    assert [(group.min_age, group.max_age) for group in groups] == [(3, 5), (6, 8)]


def test_missing_demographics_create_an_explicit_review_group():
    group = group_children(
        [Child("Do sprawdzenia", Decimal("20"), birth_year=None, gender=None)],
        reference_year=2026,
    )[0]

    assert group.needs_review is True
    assert "Płeć do weryfikacji" in group.name
    assert "wiek do weryfikacji" in group.name
