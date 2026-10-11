#!/usr/bin/env bash
# Альфа-версия Gigo в Telegram бесплатно, прямо с этого компьютера.
#
#   ./scripts/alpha.sh
#
# Собирает Mini App, запускает API и бота и открывает временный HTTPS-адрес через Cloudflare Tunnel
# или localhost.run через ssh (оба бесплатны, без регистрации). Адрес меняется при каждом запуске,
# бот сам ставит новый в кнопку меню.
# Пока скрипт работает и компьютер не спит, приложение доступно в Telegram. Остановить: Ctrl+C.
#
# Нужно один раз: Docker Desktop, backend/.venv (см. README), Node 22; cloudflared желателен, но не обязателен.
# В .env должны быть BOT_TOKEN и, по желанию, VITE_YANDEX_MAPS_KEY, YANDEX_GEOCODER_KEY, ADMIN_IDS.

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LOGS="$ROOT/data/alpha"
mkdir -p "$LOGS"
PORT="${PORT:-8000}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "Нет docker в PATH. Запустите Docker Desktop."
command -v npm >/dev/null || die "Нет Node.js (npm). Установите Node 22."
[ -x backend/.venv/bin/python ] || die "Нет backend/.venv. Создайте по README: python -m venv .venv && pip install -r requirements.txt"
[ -f .env ] || die "Нет файла .env (образец в .env.example)."
grep -Eq '^BOT_TOKEN=.+' .env || die "В .env не задан BOT_TOKEN."

PIDS=()
cleanup() {
  say "Останавливаю…"
  for pid in "${PIDS[@]}" ${TUNNEL_PID:-}; do kill "$pid" 2>/dev/null || true; done
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
# Имя бота для ссылок «Поделиться»: берём у Telegram по токену, если не задано в .env.
if ! grep -Eq '^VITE_BOT_USERNAME=.+' .env; then
  TOKEN="$(grep -E '^BOT_TOKEN=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
  export VITE_BOT_USERNAME="$(curl -fs "https://api.telegram.org/bot${TOKEN}/getMe" \
    | grep -Eo '"username":"[^"]+"' | head -1 | cut -d'"' -f4 || true)"
  unset TOKEN
fi
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
# Сначала Cloudflare (cloudflared), если его нет или он не пробился, то localhost.run через обычный ssh.
# Выбрать вручную: TUNNEL=cloudflare или TUNNEL=ssh.
URL=""
TUNNEL_PID=""

wait_url() {  # $1: шаблон адреса в логе
  URL=""
  for _ in $(seq 1 45); do
    URL="$(grep -Eo "$1" "$LOGS/tunnel.log" | head -1 || true)"
    [ -n "$URL" ] && return 0
    kill -0 "$TUNNEL_PID" 2>/dev/null || return 1
    sleep 1
  done
  return 1
}

reachable() {  # адрес отвечает снаружи
  for _ in $(seq 1 20); do
    curl -fs --max-time 5 "$URL/api/health" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

stop_tunnel() { [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null || true; TUNNEL_PID=""; }

try_cloudflare() {
  command -v cloudflared >/dev/null || { echo "cloudflared не установлен"; return 1; }
  # http2 вместо QUIC: UDP часто режут провайдеры и VPN.
  TUNNEL_TRANSPORT_PROTOCOL="${TUNNEL_TRANSPORT_PROTOCOL:-http2}" \
    cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" > "$LOGS/tunnel.log" 2>&1 &
  TUNNEL_PID=$!
  wait_url 'https://[a-z0-9-]+\.trycloudflare\.com' && reachable && return 0
  echo "Cloudflare не отвечает (подробности в tunnel.log)"
  stop_tunnel
  return 1
}

try_ssh() {
  ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -T \
    -R "80:127.0.0.1:$PORT" nokey@localhost.run > "$LOGS/tunnel.log" 2>&1 < /dev/null &
  TUNNEL_PID=$!
  wait_url 'https://[a-z0-9-]+\.lhr\.life' && reachable && return 0
  echo "localhost.run не отвечает (подробности в tunnel.log)"
  stop_tunnel
  return 1
}

case "${TUNNEL:-auto}" in
  cloudflare) try_cloudflare ;;
  ssh) try_ssh ;;
  *) try_cloudflare || try_ssh ;;
esac || die "Ни один туннель не поднялся. Чаще всего мешает VPN или провайдер: включите в VPN режим «весь трафик» и запустите снова."
PIDS+=("$TUNNEL_PID")

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
