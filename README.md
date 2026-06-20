# System SUMO — protokoły i drabinki zawodów

Aplikacja webowa, która pomaga sędziom sumo układać listy walk, generować
drabinki turniejowe (krzyżówki „każdy z każdym” oraz drabinki pucharowe),
i drukować je na arkuszach A4 (Excel / PDF). Interfejs jest po polsku.

## Funkcje

- **Konta i logowanie** — rejestracja, logowanie (login lub e-mail), wylogowanie,
  resetowanie hasła kodem wysyłanym na e-mail. Sesja w podpisanym ciasteczku.
- **Uprawnienia** — każdą soutěž (zawody) tworzy właściciel z pełnymi prawami
  (`create / update / read / delete`). Może je udostępnić innym użytkownikom w
  trybie *odczyt* lub *edycja*.
- **Zawody** — lista z paginacją, tworzenie, usuwanie (z potwierdzeniem),
  udostępnianie.
- **Import uczestników** — wgrywanie wielu plików Excel; każdy arkusz to
  kategoria wiekowa. Wymagane kolumny: `Name and Surname`, `Year of Birth`,
  `Weight category`, `Team` (pozostałe kolumny opcjonalne).
- **Kategorie** — wiekowe → wagowe → uczestnicy (edytowalna tabela).
- **Losowanie i rundy** — tasowanie kolejności (drag-n-drop), tworzenie rund.
  Runda 1 generuje drabinkę dla aktualnych uczestników; kolejne rundy tworzy się
  podając liczbę uczestników.
- **Reguły drabinek** (zgodne z arkuszami WOZP / „krzyżówki SUMO”):
  - grupa ≤ 5 zawodników → system kołowy „każdy z każdym” (Berger), z polami
    `wl` (wolny los / odpoczynek) dla nieparzystej liczby,
  - większe stawki → podział na **Grupę A** i **Grupę B**, finałowy crossover
    `A1–B2`, `B1–A2`, oraz dwa brązowe medale (repasaż, miejsca 1, 2, 3, 3).
- **Eksport A4** — `Download as Excel/PDF` oraz wersje *do sędziowania*
  (dodatkowa kolumna `Win`).

## Stos technologiczny

FastAPI + Jinja2 + HTMX + SortableJS · SQLAlchemy 2 · Alembic · PostgreSQL ·
openpyxl (Excel) · ReportLab (PDF, z osadzoną czcionką DejaVu dla polskich znaków).

## Szybki start (Docker)

```bash
cp .env.example .env          # ustaw SECRET_KEY (długi losowy ciąg)
docker compose up --build
```

Aplikacja: http://localhost:8000 . Migracje uruchamiają się automatycznie przy
starcie kontenera. Domyślnie e-maile resetu hasła trafiają do logów kontenera
(`EMAIL_BACKEND=console`) — w produkcji ustaw `EMAIL_BACKEND=smtp` i dane SMTP.

## Uruchomienie lokalne (bez Dockera)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export PYTHONPATH=src
export DATABASE_URL="postgresql+psycopg2://sumo:sumo@localhost:5432/sumo"
export SECRET_KEY="dev"
alembic upgrade head
uvicorn app.main:app --reload --app-dir src
```

Do szybkich prób można użyć SQLite: `export DATABASE_URL="sqlite:///./dev.db"`.

## Dane przykładowe

```bash
python scripts/generate_sample_data.py   # zapisuje pliki .xlsx do data/
```

W `data/` znajdują się gotowe pliki Excel z syntetycznymi (polskimi) danymi,
które można wgrać przez „Dodaj dokumenty”.

## Testy

```bash
export PYTHONPATH=src
pytest                # 21 testów: drabinki, import, auth, uprawnienia, eksport, flow
pytest --cov=app      # z pokryciem
```

## Struktura

```
src/app/            kod aplikacji (FastAPI)
  routers/          trasy: auth, competitions, categories, participants, rounds, exports
  services/         logika: excel_import, brackets, exports_excel, exports_pdf
  templates/        widoki Jinja2 (+ partials/)
  static/           CSS, JS, czcionki
src/migrations/     migracje Alembic
tests/              testy pytest
data/               przykładowe pliki Excel
scripts/            start.sh, generator danych
```

## Wdrożenie

Patrz sekcja **„Wdrożenie na darmowym hostingu”** w [CLAUDE.md](CLAUDE.md) —
opisuje krok po kroku Render.com (darmowy web service + darmowy PostgreSQL).
W repo jest gotowy plik `render.yaml` (Blueprint).
