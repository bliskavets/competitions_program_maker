#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Автоматический деплой: PostgreSQL на Neon + web-сервис на Render.
#
# Запуск:   deploy/deploy.sh
# Требует:  curl, jq, openssl  и заполненный deploy/.env.deploy
#
# Скрипт идемпотентный: повторный запуск не создаёт дубликаты (база Neon
# сохраняется в DATABASE_URL внутри .env.deploy, сервис Render ищется по имени).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$HERE/.env.deploy"

die() { echo "❌ $*" >&2; exit 1; }
info() { echo "▶ $*"; }
ok()   { echo "✅ $*"; }

# ── 1. Загрузка токенов ──────────────────────────────────────────────────────
[ -f "$ENV_FILE" ] || die "Нет файла $ENV_FILE. Скопируй .env.deploy.example и впиши токены."
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

[ -n "${NEON_API_KEY:-}" ]   || die "NEON_API_KEY пуст в $ENV_FILE (см. deploy/TOKENY.md)."
[ -n "${RENDER_API_KEY:-}" ] || die "RENDER_API_KEY пуст в $ENV_FILE (см. deploy/TOKENY.md)."
: "${NEON_PROJECT_NAME:=sumo-protokoly}"
: "${NEON_REGION:=aws-eu-central-1}"
: "${RENDER_SERVICE_NAME:=sumo-protokoly}"
: "${RENDER_REGION:=frankfurt}"
: "${GIT_REPO:=https://github.com/bliskavets/competitions_program_maker}"
: "${GIT_BRANCH:=main}"

for bin in curl jq openssl; do command -v "$bin" >/dev/null || die "Не найден $bin"; done

NEON_API="https://console.neon.tech/api/v2"
RENDER_API="https://api.render.com/v1"

# Записать/обновить ключ в .env.deploy (чтобы повторный запуск переиспользовал базу)
persist() { # persist KEY VALUE — значение пишем в кавычках (URL содержит & и ?,
            # без кавычек `source` ломается на символе &)
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    local esc; esc=$(printf '%s' "$val" | sed -e 's/[\/&|]/\\&/g')
    sed -i "s|^${key}=.*|${key}=\"${esc}\"|" "$ENV_FILE"
  else
    printf '%s="%s"\n' "$key" "$val" >> "$ENV_FILE"
  fi
}

# ── 2. База данных на Neon ───────────────────────────────────────────────────
if [ -n "${DATABASE_URL:-}" ]; then
  ok "DATABASE_URL уже задан в .env.deploy — пропускаю создание базы Neon."
else
  # Org-scoped ключи Neon требуют org_id внутри объекта project — определяем автоматически
  ORG_ID="${NEON_ORG_ID:-}"
  if [ -z "$ORG_ID" ]; then
    ORG_ID=$(curl -s "$NEON_API/users/me/organizations" \
      -H "Authorization: Bearer $NEON_API_KEY" | jq -r '.organizations[0].id // empty')
  fi

  info "Создаю проект Neon «$NEON_PROJECT_NAME» (регион $NEON_REGION, org=${ORG_ID:-personal})…"
  proj_body=$(jq -n --arg name "$NEON_PROJECT_NAME" --arg region "$NEON_REGION" --arg org "$ORG_ID" \
    '{project: ({name:$name, region_id:$region, pg_version:16} + (if $org=="" then {} else {org_id:$org} end))}')
  resp=$(curl -s -w '\n%{http_code}' -X POST "$NEON_API/projects" \
    -H "Authorization: Bearer $NEON_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$proj_body")
  code=$(echo "$resp" | tail -n1); body=$(echo "$resp" | sed '$d')
  [ "$code" = "201" ] || die "Neon вернул HTTP $code: $body"

  DATABASE_URL=$(echo "$body" | jq -r '.connection_uris[0].connection_uri')
  [ -n "$DATABASE_URL" ] && [ "$DATABASE_URL" != "null" ] || die "Не удалось получить connection_uri из ответа Neon: $body"
  # Гарантируем SSL (Neon требует)
  [[ "$DATABASE_URL" == *"sslmode="* ]] || DATABASE_URL="${DATABASE_URL}?sslmode=require"

  persist DATABASE_URL "$DATABASE_URL"
  ok "База Neon создана, DATABASE_URL сохранён в .env.deploy."
fi

# ── 3. Web-сервис на Render ──────────────────────────────────────────────────
info "Определяю владельца Render-аккаунта…"
OWNER_ID=$(curl -s "$RENDER_API/owners?limit=1" \
  -H "Authorization: Bearer $RENDER_API_KEY" | jq -r '.[0].owner.id')
[ -n "$OWNER_ID" ] && [ "$OWNER_ID" != "null" ] || die "Не удалось получить ownerId — проверь RENDER_API_KEY."
ok "ownerId = $OWNER_ID"

info "Проверяю, существует ли сервис «$RENDER_SERVICE_NAME»…"
EXISTING=$(curl -s "$RENDER_API/services?name=$RENDER_SERVICE_NAME&limit=1" \
  -H "Authorization: Bearer $RENDER_API_KEY" | jq -r '.[0].service.id // empty')

if [ -n "$EXISTING" ]; then
  ok "Сервис уже существует (id=$EXISTING) — запускаю новый деплой."
  SERVICE_ID="$EXISTING"
  # Обновим DATABASE_URL на случай, если база пересоздавалась
  curl -s -X PUT "$RENDER_API/services/$SERVICE_ID/env-vars" \
    -H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" \
    -d "[{\"key\":\"DATABASE_URL\",\"value\":\"$DATABASE_URL\"},{\"key\":\"EMAIL_BACKEND\",\"value\":\"console\"},{\"key\":\"PAGE_SIZE\",\"value\":\"10\"}]" >/dev/null || true
  curl -s -X POST "$RENDER_API/services/$SERVICE_ID/deploys" \
    -H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" -d '{}' >/dev/null
else
  SECRET_KEY=$(openssl rand -hex 32)
  info "Создаю web-сервис на Render (Docker, план free, регион $RENDER_REGION)…"
  payload=$(jq -n \
    --arg name "$RENDER_SERVICE_NAME" --arg owner "$OWNER_ID" \
    --arg repo "$GIT_REPO" --arg branch "$GIT_BRANCH" --arg region "$RENDER_REGION" \
    --arg secret "$SECRET_KEY" --arg dburl "$DATABASE_URL" '{
      type: "web_service",
      name: $name,
      ownerId: $owner,
      repo: $repo,
      branch: $branch,
      autoDeploy: "yes",
      serviceDetails: {
        runtime: "docker",
        plan: "free",
        region: $region,
        healthCheckPath: "/healthz",
        envSpecificDetails: { dockerfilePath: "./Dockerfile", dockerContext: "." }
      },
      envVars: [
        { key: "SECRET_KEY",    value: $secret },
        { key: "EMAIL_BACKEND", value: "console" },
        { key: "PAGE_SIZE",     value: "10" },
        { key: "DATABASE_URL",  value: $dburl }
      ]
    }')
  resp=$(curl -s -w '\n%{http_code}' -X POST "$RENDER_API/services" \
    -H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" \
    -d "$payload")
  code=$(echo "$resp" | tail -n1); body=$(echo "$resp" | sed '$d')
  [ "$code" = "201" ] || die "Render вернул HTTP $code: $body"
  SERVICE_ID=$(echo "$body" | jq -r '.service.id')
  ok "Сервис создан (id=$SERVICE_ID). Render запустил первый билд."
fi

# ── 4. Итог ──────────────────────────────────────────────────────────────────
URL=$(curl -s "$RENDER_API/services/$SERVICE_ID" \
  -H "Authorization: Bearer $RENDER_API_KEY" | jq -r '.serviceDetails.url // empty')
echo
ok "Готово."
echo "   Сервис:    https://dashboard.render.com/web/$SERVICE_ID"
[ -n "$URL" ] && echo "   Адрес app: $URL"
echo "   Билд идёт 3–7 минут. Прогресс — на странице сервиса (вкладка Logs/Events)."
echo "   Первый запуск применит миграции (alembic upgrade head) автоматически."
