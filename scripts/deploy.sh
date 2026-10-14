#!/usr/bin/env bash
# Запуск и обновление Gigo на сервере (после deploy/server-setup.sh):
#
#   cd ~/gigo && ./scripts/deploy.sh
#
# Первый запуск задаёт вопросы и создаёт .env (токен бота, домен, ключи карт), сам придумывает пароль базы.
# Дальше тот же скрипт обновляет сервер: подтягивает свежий код из GitHub, пересобирает и перезапускает сервисы,
# проверяет, что сайт открывается по HTTPS. Данные в базе сохраняются.
#
#   SKIP_PULL=1 ./scripts/deploy.sh   # не обновлять код из GitHub

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "Нет Docker. Сначала запустите deploy/server-setup.sh."
docker compose version >/dev/null 2>&1 || die "Нет docker compose. Сначала запустите deploy/server-setup.sh."
docker info >/dev/null 2>&1 || die "Нет доступа к Docker. Перезайдите по SSH (группа docker применяется при новом входе)."

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r' || true; }
env_set() {
  local key="$1" val="$2"
  if grep -qE "^$key=" .env; then
    # Значения (токены, ключи) не содержат «|», поэтому он годится как разделитель для sed.
    sed -i "s|^$key=.*|$key=$val|" .env
  else
    echo "$key=$val" >> .env
  fi
}
ask() {  # ask KEY "Вопрос" [обязательно]
  local key="$1" q="$2" required="${3:-}" cur val
  cur="$(env_get "$key")"
  [ -n "$cur" ] && return 0
  while :; do
    read -r -p "$q: " val </dev/tty || true
    val="$(printf '%s' "$val" | tr -d ' \r')"
    [ -n "$val" ] || [ -z "$required" ] && break
    echo "  это поле нужно заполнить"
  done
  env_set "$key" "$val"
}

if [ "${SKIP_PULL:-}" != 1 ] && [ -d .git ]; then
  say "1/6 Свежий код"
  git pull --ff-only || warn "git pull не удался (локальные правки?), продолжаю с текущим кодом"
else
  say "1/6 Код как есть"
fi

say "2/6 Настройки (.env)"
FIRST_RUN=""
if [ ! -f .env ]; then
  FIRST_RUN=1
  cp .env.example .env
  chmod 600 .env
  echo "Создаю .env. Ответы можно поменять позже: nano ~/gigo/.env и снова ./scripts/deploy.sh"
fi
ask BOT_TOKEN "Токен бота от @BotFather" required
ask DOMAIN "Домен приложения, например gigo-app.ru (без https://)" required
DOMAIN="$(env_get DOMAIN)"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN%/}"
env_set DOMAIN "$DOMAIN"
[ -n "$(env_get WEBAPP_URL)" ] && [[ "$(env_get WEBAPP_URL)" != *"$DOMAIN"* ]] \
  && warn "WEBAPP_URL ($(env_get WEBAPP_URL)) не совпадает с доменом, ставлю https://$DOMAIN"
env_set WEBAPP_URL "https://$DOMAIN"
if [ -n "$FIRST_RUN" ]; then
  ask VITE_YANDEX_MAPS_KEY "Ключ JavaScript API Яндекс Карт (Enter, чтобы пропустить)"
  ask YANDEX_GEOCODER_KEY "Ключ HTTP Геокодера Яндекса (Enter, чтобы пропустить)"
  ask ADMIN_IDS "Ваш Telegram id для модерации, узнать у @userinfobot (Enter, чтобы пропустить)"
fi
env_set DEV_AUTH 0

# Пароль базы: на сервере не оставляем учебный «gigo». Меняем только пока базы ещё нет:
# у существующей базы пароль уже записан внутри, и после замены API к ней не подключится.
DB_VOLUME="$(basename "$ROOT")_pgdata"
if [ "$(env_get POSTGRES_PASSWORD)" = gigo ] || [ -z "$(env_get POSTGRES_PASSWORD)" ]; then
  if docker volume inspect "$DB_VOLUME" >/dev/null 2>&1; then
    warn "База уже создана с паролем «gigo». Она закрыта от интернета, но пароль лучше сменить (docs/deploy.md)."
  else
    PW="$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    env_set POSTGRES_PASSWORD "$PW"
    env_set DATABASE_URL "postgresql://gigo:$PW@db:5432/gigo"
    unset PW
    echo "Пароль базы сгенерирован и записан в .env"
  fi
fi

# Имя бота для ссылок «Поделиться»: спрашиваем у Telegram по токену.
if [ -z "$(env_get VITE_BOT_USERNAME)" ]; then
  NAME="$(curl -fs "https://api.telegram.org/bot$(env_get BOT_TOKEN)/getMe" \
    | grep -Eo '"username":"[^"]+"' | head -1 | cut -d'"' -f4 || true)"
  if [ -n "$NAME" ]; then
    env_set VITE_BOT_USERNAME "$NAME"
    echo "Бот: @$NAME"
  else
    warn "Telegram не узнал токен бота. Проверьте BOT_TOKEN в .env."
  fi
fi

say "3/6 Домен смотрит на этот сервер?"
MY_IP="$(curl -4 -fs --max-time 5 https://api.ipify.org || curl -4 -fs --max-time 5 https://ifconfig.me || true)"
DNS_IP="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)"
if [ -z "$DNS_IP" ]; then
  warn "Домен $DOMAIN пока не находится в DNS. Проверьте A-запись у регистратора; обновление может занять до нескольких часов."
  warn "Без этого HTTPS-сертификат не выпустится. Можно продолжить: Caddy будет пробовать сам, пока DNS не обновится."
elif [ -n "$MY_IP" ] && [ "$DNS_IP" != "$MY_IP" ]; then
  warn "Домен $DOMAIN указывает на $DNS_IP, а у сервера IP $MY_IP. Исправьте A-запись у регистратора."
else
  echo "$DOMAIN → $DNS_IP, всё верно"
fi

say "4/6 Сборка и запуск (первый раз несколько минут)"
docker compose --profile prod up -d --build --remove-orphans

say "5/6 Проверка"
ok=""
for _ in $(seq 1 60); do
  if docker compose --profile prod exec -T api python -c \
      "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" >/dev/null 2>&1; then
    ok=1; break
  fi
  sleep 2
done
[ -n "$ok" ] || { docker compose --profile prod logs --tail 40 api; die "API не отвечает, логи выше."; }
echo "API работает"

STATIONS="$(docker compose exec -T db psql -U "${POSTGRES_USER:-gigo}" -d "${POSTGRES_DB:-gigo}" -tAc \
  'SELECT count(*) FROM metro_stations' 2>/dev/null || echo 0)"
if [ "${STATIONS:-0}" = 0 ]; then
  echo "Загружаю станции метро…"
  docker compose --profile prod exec -T api python -m gigo.metro || warn "Станции метро не загрузились, повторите ./scripts/deploy.sh позже"
fi

HTTPS=""
for _ in $(seq 1 30); do
  curl -fs --max-time 5 "https://$DOMAIN/api/health" >/dev/null 2>&1 && { HTTPS=1; break; }
  sleep 3
done
if [ -n "$HTTPS" ]; then
  echo "https://$DOMAIN открывается, сертификат в порядке"
else
  warn "https://$DOMAIN пока не открывается. Обычно это DNS: дождитесь A-записи, Caddy выпустит сертификат сам."
  warn "Что происходит: docker compose --profile prod logs --tail 30 web"
fi
docker compose --profile prod ps --format 'table {{.Service}}\t{{.Status}}'

say "6/6 Ежедневная копия базы"
CRON_LINE="30 4 * * * $ROOT/scripts/backup.sh >> $ROOT/backups/backup.log 2>&1"
mkdir -p backups
if ! command -v crontab >/dev/null; then
  warn "Нет cron (sudo apt install cron), копии пока делайте вручную: ./scripts/backup.sh"
elif ! crontab -l 2>/dev/null | grep -qF "$ROOT/scripts/backup.sh"; then
  (crontab -l 2>/dev/null || true; echo "$CRON_LINE") | crontab -
  echo "Каждую ночь в 4:30 копия кладётся в $ROOT/backups (хранятся 14 последних)"
else
  echo "уже настроена"
fi

say "Готово"
if [ -n "$FIRST_RUN" ]; then
  echo "Последний шаг в @BotFather: /mybots → бот → Bot Settings → Configure Mini App → Enable Mini App →"
  echo "  URL https://$DOMAIN"
fi
echo "Кнопку «Gigo» в меню бот ставит сам. Логи: docker compose --profile prod logs -f bot"
