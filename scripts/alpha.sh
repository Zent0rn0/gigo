#!/usr/bin/env bash
# Альфа-версия Gigo в Telegram бесплатно, прямо с этого компьютера.
#
#   ./scripts/alpha.sh
#
# Собирает Mini App, запускает API и бота и открывает HTTPS-адрес через бесплатный туннель:
#   - Tailscale Funnel (если установлен Tailscale): постоянный адрес вида https://mac.tailXXXX.ts.net;
#   - ngrok (если в .env задан NGROK_DOMAIN): постоянный бесплатный домен ngrok;
#   - иначе временный адрес Cloudflare Tunnel или localhost.run, он меняется, бот сам ставит новый в кнопку меню.
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

env_get() { grep -E "^$1=" .env | head -1 | cut -d= -f2- | tr -d '"'"'"' \r' || true; }

API_PID=""; TUNNEL_PID=""""; BOT_PID=""; AWAKE_PID=""
cleanup() {
  say "Останавливаю…"
  for pid in $API_PID $TUNNEL_PID $BOT_PID $AWAKE_PID; do kill "$pid" 2>/dev/null || true; done
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
API_PID=$!
for _ in $(seq 1 30); do
  curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null || die "API не запустился, подробности: $LOGS/api.log"

say "4/5 Туннель"
# Сначала туннели с постоянным адресом (ngrok со своим доменом, Tailscale Funnel): старые кнопки в чате продолжают
# работать. Потом временные: Cloudflare, затем localhost.run через обычный ssh.
# Выбрать вручную: TUNNEL=ngrok, TUNNEL=tailscale, TUNNEL=cloudflare или TUNNEL=ssh.
NGROK_DOMAIN="${NGROK_DOMAIN:-$(env_get NGROK_DOMAIN)}"
NGROK_DOMAIN="${NGROK_DOMAIN#https://}"; NGROK_DOMAIN="${NGROK_DOMAIN%/}"
TS="$(command -v tailscale || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale)"
URL=""

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

try_ngrok() {
  [ -n "$NGROK_DOMAIN" ] || { echo "NGROK_DOMAIN не задан в .env"; return 1; }
  command -v ngrok >/dev/null || { echo "ngrok не установлен (brew install ngrok)"; return 1; }
  ngrok http "$PORT" --url "https://$NGROK_DOMAIN" --log stdout > "$LOGS/tunnel.log" 2>&1 &
  TUNNEL_PID=$!
  wait_url "https://${NGROK_DOMAIN//./\\.}" && reachable && return 0
  echo "ngrok не отвечает (подробности в tunnel.log; вход: ngrok config add-authtoken <токен>)"
  stop_tunnel
  return 1
}

try_tailscale() {
  [ -x "$TS" ] || { echo "Tailscale не установлен"; return 1; }
  "$TS" status >/dev/null 2>&1 || { echo "Tailscale не запущен или не выполнен вход"; return 1; }
  "$TS" funnel "$PORT" > "$LOGS/tunnel.log" 2>&1 < /dev/null &
  TUNNEL_PID=$!
  wait_url 'https://[a-z0-9-]+\.[a-z0-9-]+\.ts\.net' && URL="${URL%/}" && reachable && return 0
  if grep -q 'login.tailscale.com' "$LOGS/tunnel.log"; then
    echo "Funnel не включён. Включите по ссылке и запустите скрипт снова:"
    grep -Eo 'https://login\.tailscale\.com[^ ]+' "$LOGS/tunnel.log" | head -1
  else
    echo "Tailscale Funnel не отвечает (подробности в tunnel.log)"
  fi
  stop_tunnel
  return 1
}

start_tunnel() {
  case "${TUNNEL:-auto}" in
    ngrok) try_ngrok ;;
    tailscale) try_tailscale ;;
    cloudflare) try_cloudflare ;;
    ssh) try_ssh ;;
    *) { [ -n "$NGROK_DOMAIN" ] && try_ngrok; } || { [ -x "$TS" ] && try_tailscale; } || try_cloudflare || try_ssh ;;
  esac
}

start_tunnel || die "Ни один туннель не поднялся. Чаще всего мешает VPN или провайдер: включите в VPN режим «весь трафик» и запустите снова."

say "5/5 Бот"
start_bot() {  # бот при старте ставит текущий адрес в кнопку меню
  [ -n "$BOT_PID" ] && kill "$BOT_PID" 2>/dev/null && wait "$BOT_PID" 2>/dev/null || true
  ( cd backend && DEV_AUTH=0 WEBAPP_URL="$URL" exec .venv/bin/python -m gigo.bot ) >> "$LOGS/bot.log" 2>&1 &
  BOT_PID=$!
}
start_bot

say "Готово: $URL"
echo "Откройте своего бота в Telegram и нажмите кнопку «Gigo» слева от поля ввода."
echo "Логи: $LOGS (api.log, bot.log, tunnel.log). Остановить: Ctrl+C."
echo "Мак не уснёт, пока работает скрипт. Если туннель оборвётся, скрипт поднимет новый и обновит кнопку в боте."
case "$URL" in *.ts.net|*ngrok*) ;; *)
  echo "Адрес временный: при смене старые кнопки в чате перестают открываться («no tunnel»)."
  echo "Постоянный адрес бесплатно: установите Tailscale и включите Funnel (README, раздел «Альфа»)." ;;
esac

# Не даём компьютеру уснуть, пока жив API.
if command -v caffeinate >/dev/null; then caffeinate -i -w "$API_PID" & AWAKE_PID=$!; fi

# sleep в фоне + wait: так Ctrl+C и kill срабатывают сразу, а не после паузы.
nap() { sleep "$1" & wait $! || true; }

# Сторож: туннель бесплатный и иногда обрывается или меняет адрес. Тогда поднимаем новый и перезапускаем бота.
fails=0
while true; do
  nap 10
  kill -0 "$API_PID" 2>/dev/null || die "API остановился. Последние строки: $(tail -5 "$LOGS/api.log" 2>/dev/null)"
  # localhost.run сам меняет адрес, не разрывая соединение: новый адрес появляется в его логе.
  NEW="$(grep -Eo 'https://[a-z0-9-]+\.(lhr\.life|trycloudflare\.com)' "$LOGS/tunnel.log" | tail -1 || true)"
  if [ -n "$NEW" ] && [ "$NEW" != "$URL" ]; then
    URL="$NEW"
    fails=0
    start_bot
    echo "$(date '+%H:%M') туннель сменил адрес: $URL, кнопка в боте обновлена"
    continue
  fi
  if kill -0 "$TUNNEL_PID" 2>/dev/null && curl -fs --max-time 10 "$URL/api/health" >/dev/null 2>&1; then
    fails=0
  else
    fails=$((fails + 1))
  fi
  if [ "$fails" -ge 4 ] || ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo "$(date '+%H:%M') туннель $URL не отвечает, поднимаю новый…"
    stop_tunnel
    if start_tunnel; then
      fails=0
      start_bot
      echo "$(date '+%H:%M') новый адрес: $URL, кнопка в боте обновлена"
    else
      echo "$(date '+%H:%M') туннель не поднялся, попробую ещё раз через минуту"
      nap 40
    fi
  elif ! kill -0 "$BOT_PID" 2>/dev/null; then
    echo "$(date '+%H:%M') бот остановился, перезапускаю (подробности в bot.log)"
    start_bot
  fi
done
