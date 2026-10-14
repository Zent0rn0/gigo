#!/usr/bin/env bash
# Ретранслятор Telegram API для бота Gigo. Нужен, потому что с российских серверов api.telegram.org недоступен.
# Ставится на маленький зарубежный VPS (Ubuntu 22.04/24.04), один раз, от root:
#
#   curl -fsSL https://raw.githubusercontent.com/Zent0rn0/gigo/main/deploy/relay-setup.sh | bash -s -- tg.вашдомен.ru IP_основного_сервера
#
# Что делает: ставит Caddy, который по адресу https://tg.вашдомен.ru пересылает запросы бота в api.telegram.org.
# HTTPS-сертификат выпускается сам. Пускает только основной сервер (по IP), остальным отвечает 403.
# На основном сервере в .env: TELEGRAM_API_URL=https://tg.вашдомен.ru
# Повторный запуск с другим IP просто обновляет настройку.

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
RELAY_DOMAIN="${1:-}"
MAIN_IP="${2:-}"
UPSTREAM="${UPSTREAM:-https://api.telegram.org}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "Запустите от root (или через sudo)."
[ -n "$RELAY_DOMAIN" ] && [ -n "$MAIN_IP" ] \
  || die "Укажите домен ретранслятора и IP основного сервера: bash -s -- tg.вашдомен.ru 185.12.34.56"
[[ "$MAIN_IP" =~ ^[0-9.]+$|: ]] || die "Второй параметр должен быть IP-адресом основного сервера, а не «$MAIN_IP»."
RELAY_DOMAIN="${RELAY_DOMAIN#https://}"; RELAY_DOMAIN="${RELAY_DOMAIN%/}"

say "1/4 Система"
apt-get update -q
apt-get -yq -o Dpkg::Options::=--force-confold upgrade
apt-get -yq install ca-certificates curl ufw fail2ban unattended-upgrades
echo 'unattended-upgrades unattended-upgrades/enable_auto_updates boolean true' | debconf-set-selections
dpkg-reconfigure -f noninteractive unattended-upgrades

say "2/4 Caddy"
command -v caddy >/dev/null || apt-get -yq install caddy
cat > /etc/caddy/Caddyfile <<CADDY
# Ретранслятор Telegram API для Gigo (deploy/relay-setup.sh)
$RELAY_DOMAIN {
	@main remote_ip $MAIN_IP
	handle @main {
		reverse_proxy $UPSTREAM {
			header_up Host {upstream_hostport}
			flush_interval -1
		}
	}
	handle {
		respond 403
	}
}
CADDY
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable caddy >/dev/null 2>&1 || true
systemctl restart caddy

say "3/4 Фаервол"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable
systemctl enable --now fail2ban
if [ -s /root/.ssh/authorized_keys ]; then
  printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' > /etc/ssh/sshd_config.d/99-gigo.conf
  mkdir -p /run/sshd
  sshd -t && (systemctl reload ssh 2>/dev/null || systemctl reload sshd)
  echo "Вход по SSH только по ключу"
fi

say "4/4 Проверка"
ok=""
for _ in $(seq 1 30); do
  # Сертификат появится, когда A-запись $RELAY_DOMAIN укажет на этот сервер. Ответ 403 значит, что HTTPS уже работает.
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "https://$RELAY_DOMAIN/" || true)"
  [ "$code" = 403 ] && { ok=1; break; }
  sleep 3
done
if [ -n "$ok" ]; then
  echo "https://$RELAY_DOMAIN работает и пускает только $MAIN_IP"
else
  echo "HTTPS пока не поднялся. Проверьте, что A-запись $RELAY_DOMAIN указывает на IP этого сервера;"
  echo "Caddy будет пробовать сам. Что происходит: journalctl -u caddy -n 30"
fi
say "Готово. На основном сервере в ~/gigo/.env впишите TELEGRAM_API_URL=https://$RELAY_DOMAIN и запустите ./scripts/deploy.sh"
