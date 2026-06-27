# Где взять токены для деплоя

Деплой полностью автоматический: приложение → **Render** (бесплатный web-сервис),
база данных → **Neon** (бесплатный PostgreSQL, не удаляется со временем).
Нужно получить **2 токена** и вставить их в `deploy/.env.deploy`.

GitHub-токен **не нужен** — репозиторий публичный, Render тянет код по URL сам.

---

## 1. NEON_API_KEY (база данных)

1. Зайди на <https://console.neon.tech> и войди (можно через GitHub).
2. Нажми на аватар/имя аккаунта (вверху справа) → **Account settings**.
3. Слева выбери **API keys** → кнопка **Create API key** ("Create new API key").
4. Дай имя (например `deploy`) → **Create**.
5. Скопируй показанный ключ (он показывается **один раз**) — это `NEON_API_KEY`.

Прямая ссылка: <https://console.neon.tech/app/settings/api-keys>

---

## 2. RENDER_API_KEY (хостинг приложения)

1. Зайди на <https://dashboard.render.com> и войди (можно через GitHub).
2. Вверху справа: аватар → **Account Settings**.
3. Слева **API Keys** → **Create API Key**.
4. Дай имя (например `deploy`) → **Create**.
5. Скопируй ключ — это `RENDER_API_KEY`.

Прямая ссылка: <https://dashboard.render.com/u/settings#api-keys>

---

## 3. Вставить токены и запустить

```bash
cp deploy/.env.deploy.example deploy/.env.deploy
# открой deploy/.env.deploy и впиши NEON_API_KEY и RENDER_API_KEY
```

Затем скажи ассистенту **«запускай деплой»** — он выполнит `deploy/deploy.sh`.
Либо вручную:

```bash
bash deploy/deploy.sh
```

Скрипт:
1. создаст проект PostgreSQL на Neon и сохранит `DATABASE_URL` в `.env.deploy`;
2. создаст web-сервис на Render (Docker, план free) с этим `DATABASE_URL`,
   сгенерированным `SECRET_KEY` и `EMAIL_BACKEND=console`;
3. Render соберёт образ, применит миграции (`alembic upgrade head`) и поднимет
   приложение. Адрес вида `https://sumo-protokoly.onrender.com` появится в выводе.

Файл `deploy/.env.deploy` добавлен в `.gitignore` — токены в git не попадут.

> ⚠️ Бесплатный web-сервис Render засыпает после ~15 минут простоя; первый
> запрос после паузы медленнее (10–30 c). Это нормально для free-плана.
