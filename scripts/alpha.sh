#!/usr/bin/env bash
# Альфа-версия Gigo в Telegram бесплатно, прямо с этого компьютера.
#
#   ./scripts/alpha.sh
#
# Собирает Mini App, запускает API и бота и открывает временный HTTPS-адрес через Cloudflare Tunnel
# (бесплатно, без регистрации). Адрес меняется при каждом запуске, бот сам ставит новый в кнопку меню.
# Пока скрипт работает и компьютер не спит, приложение доступно в Telegram. Остановить: Ctrl+C.
#
# Нужно один раз: Docker Desktop, backend/.venv (см. README), Node 22 и cloudflared (brew install cloudflared).
# В .env должны быть BOT_TOKEN и, по желанию, VITE_YANDEX_MAPS_KEY, YANDEX_GEOCODER_KEY, ADMIN_IDS.

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LOGS="$ROOT/data/alpha"
mkdir -p "$LOGS"
PORT="${PORT:-8000}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

command -v cloudflared >/dev/null || die "Нет cloudflared. Установите: brew install cloudflared"
command -v docker >/dev/null || die "Нет docker в PATH. Запустите Docker Desktop."
command -v npm >/dev/null || die "Нет Node.js (npm). Установите Node 22."
[ -x backend/.venv/bin/python ] || die "Нет backend/.venv. Создайте по README: python -m venv .venv && pip install -r requirements.txt"
[ -f .env ] || die "Нет файла .env (образец в .env.example)."
grep -Eq '^BOT_TOKEN=.+' .env || die "В .env не задан BOT_TOKEN."

PIDS=()
cleanup() {
  say "Останавливаю…"
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

say "1/5 База"
docker compose up -d db >/dev/null
for _ in $(seq 1 60); do
  docker compose exec -T db pg_isready -U gigo >/dev/null 2>&1 && break
  sleep 1
done

say "2/5 Сборка Mini App"
( cd frontend && { [ -d node_modules ] || npm ci; } && npm run build ) > "$LOGS/build.log" 2>&1 \
  || die "Сборка не удалась, подробности: $LOGS/build.log"

say "3/5 API"
# Вход только через Telegram: DEV_AUTH выключен, что бы ни было в .env.
( cd backend && DEV_AUTH=0 STATIC_DIR="$ROOT/frontend/dist" \
    exec .venv/bin/uvicorn gigo.api.app:app --host 127.0.0.1 --port "$PORT" ) > "$LOGS/api.log" 2>&1 &
PIDS+=($!)
for _ in $(seq 1 30); do
  curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null || die "API не запустился, подробности: $LOGS/api.log"

say "4/5 Туннель"
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" > "$LOGS/tunnel.log" 2>&1 &
PIDS+=($!)
URL=""
for _ in $(seq 1 60); do
  URL="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOGS/tunnel.log" | head -1 || true)"
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || die "Туннель не поднялся, подробности: $LOGS/tunnel.log"
# Ждём, пока адрес начнёт отвечать снаружи.
for _ in $(seq 1 30); do
  curl -fs "$URL/api/health" >/dev/null 2>&1 && break
  sleep 2
done

say "5/5 Бот"
( cd backend && DEV_AUTH=0 WEBAPP_URL="$URL" exec .venv/bin/python -m gigo.bot ) > "$LOGS/bot.log" 2>&1 &
PIDS+=($!)

say "Готово: $URL"
echo "Откройте своего бота в Telegram и нажмите кнопку «Gigo» слева от поля ввода."
echo "Логи: $LOGS (api.log, bot.log, tunnel.log). Остановить: Ctrl+C."
echo "Мак не уснёт, пока работает скрипт."

# Не даём компьютеру уснуть, пока живы API, туннель и бот.
if command -v caffeinate >/dev/null; then caffeinate -i -w "${PIDS[0]}" & PIDS+=($!); fi
while kill -0 "${PIDS[0]}" 2>/dev/null && kill -0 "${PIDS[1]}" 2>/dev/null && kill -0 "${PIDS[2]}" 2>/dev/null; do
  sleep 5
done
die "Что-то остановилось. Последние строки логов:
$(tail -5 "$LOGS/api.log" 2>/dev/null)
$(tail -5 "$LOGS/tunnel.log" 2>/dev/null)
$(tail -5 "$LOGS/bot.log" 2>/dev/null)"
