#!/usr/bin/env bash
# Копия базы Gigo в backups/ (scripts/deploy.sh ставит её в cron на каждую ночь). Хранятся 14 последних.
#
#   ./scripts/backup.sh
#
# Восстановить (заменит текущие данные!):
#   docker compose --profile prod stop api bot
#   gunzip -c backups/gigo-<дата>.sql.gz | docker compose exec -T db psql -q -U gigo -d gigo
#   docker compose --profile prod up -d

set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
FILE="backups/gigo-$(date +%F-%H%M).sql.gz"
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-gigo}" --clean --if-exists "${POSTGRES_DB:-gigo}" \
  | gzip > "$FILE.tmp"
mv "$FILE.tmp" "$FILE"
ls -1t backups/gigo-*.sql.gz | tail -n +15 | xargs -r rm --
echo "$(date '+%F %T') $FILE $(du -h "$FILE" | cut -f1)"
