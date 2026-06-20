"""Generate synthetic Polish participant data as Excel workbooks in data/.

Each workbook has one sheet per age category, with the required columns:
Name and Surname | Year of Birth | Weight category | Team
"""
from __future__ import annotations

import os
import random

from openpyxl import Workbook

FIRST_NAMES = [
    "Jan", "Piotr", "Kacper", "Szymon", "Filip", "Antoni", "Jakub", "Wojciech",
    "Anna", "Zofia", "Maja", "Julia", "Lena", "Hanna", "Maria", "Oliwia",
    "Mateusz", "Adam", "Aleksander", "Tomasz", "Michał", "Bartosz",
]
LAST_NAMES = [
    "Nowak", "Kowalski", "Wiśniewski", "Wójcik", "Kowalczyk", "Kamiński",
    "Lewandowski", "Zieliński", "Szymański", "Woźniak", "Dąbrowski",
    "Kozłowski", "Jankowski", "Mazur", "Kwiatkowski", "Krawczyk", "Piotrowski",
]
CLUBS = [
    "UKS Sumo Warszawa", "KS Olimpijczyk Kraków", "MKS Zawisza Bydgoszcz",
    "UKS Tatami Gdańsk", "KS Grappler Poznań", "AZS Wrocław", "LKS Sokół Lublin",
]

# age category name -> birth-year range -> weight classes (kg)
AGE_CATEGORIES = {
    "Dzieci (2016-2017)": (2016, 2017, [20, 24, 28, 32]),
    "Młodzicy (2013-2015)": (2013, 2015, [30, 35, 40, 45, 50]),
    "Kadeci (2010-2012)": (2010, 2012, [45, 50, 55, 60, 66, 73]),
    "Juniorzy (2007-2009)": (2007, 2009, [60, 66, 73, 84, 100]),
}


def _full_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def build_workbook(seed: int = 42, per_class: tuple[int, int] = (3, 8)) -> Workbook:
    rng = random.Random(seed)
    wb = Workbook()
    wb.remove(wb.active)
    for age_name, (lo, hi, weights) in AGE_CATEGORIES.items():
        ws = wb.create_sheet(title=age_name[:31])
        ws.append(["Name and Surname", "Year of Birth", "Weight category", "Team"])
        for w in weights:
            count = rng.randint(*per_class)
            for _ in range(count):
                ws.append(
                    [
                        _full_name(rng),
                        rng.randint(lo, hi),
                        f"{w} kg",
                        rng.choice(CLUBS),
                    ]
                )
    return wb


def main() -> None:
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)
    for seed, label in ((42, "zawody_warszawa"), (7, "puchar_polski")):
        wb = build_workbook(seed=seed)
        path = os.path.join(out_dir, f"przyklad_{label}.xlsx")
        wb.save(path)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
