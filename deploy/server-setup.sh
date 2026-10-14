#!/usr/bin/env bash
# Первичная настройка чистого сервера Ubuntu 22.04/24.04 под Gigo. Запускать один раз, от root:
#
#   curl -fsSL https://raw.githubusercontent.com/Zent0rn0/gigo/main/deploy/server-setup.sh | bash
#
# Что делает:
#   - обновляет систему и включает автообновления безопасности;
#   - ставит Docker (с зеркалом образов на случай блокировок Docker Hub), git, фаервол ufw и fail2ban;
#   - добавляет файл подкачки 2 ГБ, если его нет (сборке Mini App нужна память);
#   - создаёт пользователя gigo (sudo + docker) и копирует ему SSH-ключи root;
#   - открывает наружу только SSH, 80 и 443;
#   - если у gigo есть SSH-ключ, запрещает вход по паролю и вход под root;
#   - скачивает проект в /home/gigo/gigo.
# Повторный запуск безопасен.

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
REPO="${REPO:-https://github.com/Zent0rn0/gigo.git}"
APP_USER="${APP_USER:-gigo}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "Запустите от root (или через sudo)." >&2; exit 1; }

say "1/7 Обновление системы"
apt-get update -q
apt-get -yq -o Dpkg::Options::=--force-confold upgrade
apt-get -yq install ca-certificates curl git cron openssl ufw fail2ban unattended-upgrades
timedatectl set-timezone Europe/Moscow || true
echo 'unattended-upgrades unattended-upgrades/enable_auto_updates boolean true' | debconf-set-selections
dpkg-reconfigure -f noninteractive unattended-upgrades

say "2/7 Docker"
mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  # Зеркало Google: если Docker Hub недоступен из РФ, образы скачаются с него. Логи контейнеров не разрастаются.
  cat > /etc/docker/daemon.json <<'JSON'
{
  "registry-mirrors": ["https://mirror.gcr.io"],
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "5"}
}
JSON
fi
if ! docker compose version >/dev/null 2>&1; then
  # Пакеты Ubuntu не зависят от download.docker.com, который из РФ бывает недоступен.
  apt-get -yq install docker.io docker-compose-v2 docker-buildx \
    || apt-get -yq install docker.io docker-compose-v2 \
    || curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
systemctl restart docker
docker compose version

say "3/7 Файл подкачки"
if [ -z "$(swapon --show --noheadings)" ]; then
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo 'vm.swappiness=10' > /etc/sysctl.d/99-gigo-swap.conf && sysctl -q -p /etc/sysctl.d/99-gigo-swap.conf
else
  echo "уже есть"
fi

say "4/7 Пользователь $APP_USER"
id "$APP_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$APP_USER"
usermod -aG sudo,docker "$APP_USER"
# sudo без пароля: у пользователя нет пароля, вход только по ключу.
echo "$APP_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$APP_USER" && chmod 440 "/etc/sudoers.d/90-$APP_USER"
HOME_DIR="$(getent passwd "$APP_USER" | cut -d: -f6)"
install -d -m 700 -o "$APP_USER" -g "$APP_USER" "$HOME_DIR/.ssh"
if [ -s /root/.ssh/authorized_keys ]; then
  touch "$HOME_DIR/.ssh/authorized_keys"
  # Добавляем ключи root, которых у пользователя ещё нет.
  NEW_KEYS="$(grep -vxFf "$HOME_DIR/.ssh/authorized_keys" /root/.ssh/authorized_keys || true)"
  [ -z "$NEW_KEYS" ] || printf '%s\n' "$NEW_KEYS" >> "$HOME_DIR/.ssh/authorized_keys"
  chown "$APP_USER:$APP_USER" "$HOME_DIR/.ssh/authorized_keys" && chmod 600 "$HOME_DIR/.ssh/authorized_keys"
fi

say "5/7 Фаервол"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 443/udp >/dev/null
ufw --force enable
ufw status | sed -n '1,12p'
systemctl enable --now fail2ban

say "6/7 SSH"
if [ -s "$HOME_DIR/.ssh/authorized_keys" ]; then
  cat > /etc/ssh/sshd_config.d/99-gigo.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
CONF
  mkdir -p /run/sshd
  sshd -t && (systemctl reload ssh 2>/dev/null || systemctl reload sshd)
  echo "Вход только по ключу, под пользователем $APP_USER: ssh $APP_USER@<IP>"
else
  warn "У $APP_USER нет SSH-ключа, поэтому вход по паролю НЕ отключён."
  warn "Добавьте ключ (docs/deploy.md, шаг про SSH) и запустите этот скрипт ещё раз."
fi

say "7/7 Проект"
if [ -d "$HOME_DIR/gigo/.git" ]; then
  sudo -u "$APP_USER" git -C "$HOME_DIR/gigo" pull --ff-only || warn "git pull не удался, проект оставлен как есть"
else
  sudo -u "$APP_USER" git clone "$REPO" "$HOME_DIR/gigo"
fi

say "Готово. Дальше:"
echo "  ssh $APP_USER@<IP сервера>"
echo "  cd ~/gigo && ./scripts/deploy.sh"
