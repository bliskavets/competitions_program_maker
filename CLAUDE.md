# CLAUDE.md — wskazówki dla kolejnych wersji asystenta

Ten plik opisuje architekturę i konwencje projektu, żeby kolejna sesja mogła
płynnie kontynuować pracę. (Krótko po polsku/angielsku — kod i komentarze są
mieszane, interfejs po polsku.)

## Co to jest

Aplikacja webowa dla sędziów sumo: konta + uprawnienia, import uczestników z
Excela, generowanie krzyżówek/drabinek i eksport na A4 (Excel/PDF). Stos:
**FastAPI + Jinja2 + HTMX + SortableJS**, **SQLAlchemy 2 + Alembic**,
**PostgreSQL**, **openpyxl**, **ReportLab**.

## Mapa kodu

| Ścieżka | Rola |
|---|---|
| `src/app/main.py` | Tworzy `FastAPI`, montuje statyki, podpina routery, handler `LoginRedirect`. |
| `src/app/config.py` | `Settings` (pydantic-settings) + `sqlalchemy_url` (normalizuje `postgres://`). |
| `src/app/database.py` | Engine/sesja; `get_db()` dependency; działa też na SQLite (testy). |
| `src/app/models.py` | ORM: User, PasswordReset, Competition, CompetitionPermission, AgeCategory, WeightCategory, Participant, Round. |
| `src/app/security.py` | bcrypt (passlib), podpisane ciasteczko sesji (itsdangerous), kod resetu (uuid). |
| `src/app/email_utils.py` | Wysyłka e-mail; backend `console` (log) lub `smtp`. |
| `src/app/deps.py` | `get_current_user`, `require_user`, `rights_for`, `load_competition`, `ensure`. |
| `src/app/routers/` | `auth`, `competitions`, `categories`, `participants`, `rounds`, `exports`. |
| `src/app/services/brackets.py` | **Serce**: round-robin (Berger), podział A/B, finał, drabinka pucharowa. |
| `src/app/services/excel_import.py` | Parsowanie i import arkuszy Excel. |
| `src/app/services/exports_excel.py` / `exports_pdf.py` | Eksport A4 (+ wariant „do sędziowania”). |
| `src/app/templates/` | Widoki + `partials/` (HTMX zwraca partiale). |
| `src/migrations/` | Alembic. Pierwsza rewizja tworzy schemat z `Base.metadata`. |
| `tests/` | pytest (SQLite, `TestClient`). |

## Reguły drabinek (ważne!)

Wzorzec to arkusze „krzyżówki SUMO” (plik PDF w repo) oraz przepisy WOZP:
- **≤ 5 zawodników** w grupie → system kołowy „każdy z każdym”. Schemat liczony
  metodą okręgu (`round_robin_rounds`). Dla nieparzystej liczby jeden zawodnik
  odpoczywa w danej rundzie — pole `wl` (rest_round) na arkuszu.
- **> 5** → podział na **Grupę A** i **Grupę B** (`build_initial_bracket`). Każda
  połowa: round-robin (≤5) lub drabinka pucharowa (`single_elimination`).
- **Finał**: crossover `A1–B2`, `B1–A2`, miejsca `1, 2, 3, 3` (dwa brązy =
  repasaż o 3. miejsce).
- Runda 1 generuje się z aktualnych uczestników; rundy 2+ z podanej liczby
  (`build_empty_bracket`). Dane drabinki są zapisywane jako JSON w `Round.data`.

## Konwencje

- **Migracje**: kolejne zmiany schematu dodawaj jako *osobne* rewizje Alembic
  (`alembic revision --autogenerate -m "..."`). Pierwsza rewizja celowo używa
  `create_all`, by trzymać się modeli — nie kopiuj tego wzorca dla zmian.
- **HTMX**: akcje modyfikujące pełną stronę → `RedirectResponse(303)`; fragmenty
  (share, upload, shuffle, formularz rundy) → render partiala z `templates/partials`.
- **Uprawnienia**: zawsze przez `rights_for(...)` + `ensure(rights.can_*)`.
  Właściciel ma wszystkie prawa; współdzielenie ustawia `CompetitionPermission`.
- **PDF i polskie znaki**: ReportLab używa osadzonej czcionki DejaVu
  (`static/fonts`). Nowe tabele PDF ustawiaj `FONTNAME` na `FONT` / `FONT_BOLD`,
  inaczej `ą/ę/ł/Ł` wyjdą jako kwadraty.
- **Czas/losowość**: w kodzie aplikacji wolno; w testach DB jest świeża per test.

## Co można dopracować (backlog)

- Pełna edycja drabinki w UI (obecnie edytowalne są nazwiska; wyniki wpisuje
  sędzia na wydruku). Rozważ przechowywanie wyników walk i auto-awans zwycięzców.
- Podsumowanie końcowe zawodów (miejsca wszystkich uczestników malejąco) — jest
  w specyfikacji, można dodać jako osobny widok/eksport.
- Gotowe szablony arkuszy dla każdej liczby 1–200 (specyfikacja dopuszcza) —
  najpierw potwierdź z użytkownikiem czytelność na A4 (patrz `/rounds/{id}/pdf`).
- Twardsza walidacja Excela i komunikaty błędów per-wiersz.

## Uruchamianie / testy

```bash
docker compose up --build           # pełne środowisko z Postgresem
PYTHONPATH=src pytest               # testy (SQLite)
python scripts/generate_sample_data.py   # dane przykładowe do data/
```

---

## Wdrożenie na darmowym hostingu (krok po kroku)

Najprostsza darmowa opcja na 2026: **Render.com** — jeden darmowy *web service*
(Docker) + jeden darmowy *PostgreSQL*, opisane w `render.yaml` (Blueprint).

1. Wypchnij repozytorium na GitHub (już zrobione: `bliskavets/competitions_program_maker`).
2. Załóż konto na <https://render.com> (logowanie przez GitHub).
3. **New +** → **Blueprint** → wybierz to repo. Render odczyta `render.yaml`,
   utworzy bazę `sumo-db` i serwis `sumo-protokoly`, wygeneruje `SECRET_KEY`
   i wstrzyknie `DATABASE_URL`.
4. Kliknij **Apply**. Pierwszy build zbuduje obraz Docker, `start.sh` uruchomi
   `alembic upgrade head`, a potem uvicorn. Health-check: `/healthz`.
5. Po wdrożeniu dostaniesz URL `https://sumo-protokoly.onrender.com` (subdomena
   = darmowa „nazwa domeny”). Własną domenę można podpiąć w Settings → Custom Domain.
6. **E-mail resetu hasła**: domyślnie `EMAIL_BACKEND=console` (kod w logach). Aby
   wysyłać prawdziwe maile, w Render → Environment ustaw `EMAIL_BACKEND=smtp`
   oraz `SMTP_HOST/PORT/USERNAME/PASSWORD/FROM` (np. darmowy Brevo/SendGrid).

Uwaga: darmowy web service Rendera usypia po ~15 min bezczynności (pierwsze
żądanie po przerwie jest wolniejsze). Darmowy PostgreSQL Rendera ma limit czasu —
jeśli wygaśnie, alternatywa to **Neon** (darmowy Postgres) + zmienna
`DATABASE_URL` wskazująca na Neon, albo **Koyeb** (1 darmowy serwis + 1 baza).

### Alternatywy
- **Koyeb**: 1 darmowy serwis + 1 zarządzany PostgreSQL; deploy z Dockerfile.
- **Fly.io**: kontenery + Postgres (sprawdź aktualne darmowe limity).
- **Railway**: najlepsza integracja DB, ale darmowy tier to kredyt próbny.
