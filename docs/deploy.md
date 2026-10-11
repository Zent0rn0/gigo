# Деплой на сервер

Один VPS: 2 ядра, 2–4 ГБ памяти, Ubuntu 24.04. Всё запускается одним `docker compose`; HTTPS-сертификат Caddy получает сам.

## 1. Сервер и домен

1. Арендуйте VPS, зайдите по SSH.
2. Направьте домен (например `gigo.example.ru`) A-записью на IP сервера.
3. Установите Docker:

```bash
curl -fsSL https://get.docker.com | sh
```

## 2. Код и настройки

```bash
git clone https://github.com/<вы>/gigo.git && cd gigo
cp .env.example .env && nano .env
```

В `.env` для сервера обязательно:

| Переменная | Значение |
|---|---|
| `BOT_TOKEN` | токен бота |
| `YANDEX_GEOCODER_KEY`, `VITE_YANDEX_MAPS_KEY` | карты |
| `DOMAIN` | `gigo.example.ru` |
| `WEBAPP_URL` | `https://gigo.example.ru` |
| `POSTGRES_PASSWORD` | длинный случайный пароль |
| `DEV_AUTH` | `0` |

## 3. Запуск

```bash
docker compose --profile prod build
docker compose up -d db
docker compose --profile prod run --rm api python -m gigo.migrate
docker compose --profile prod run --rm api python -m gigo.metro
docker compose --profile prod up -d
```

## 4. Mini App в боте

В @BotFather: `/mybots` → бот → Bot Settings → Configure Mini App → Enable Mini App → URL `https://gigo.example.ru`.
Кнопку меню «Gigo» бот ставит сам при старте, если задан `WEBAPP_URL`.

## 5. Наблюдение

```bash
docker compose --profile prod ps                       # все сервисы должны быть Up, api — healthy
docker compose --profile prod logs -f bot              # «отправлено событий: 3»
curl https://gigo.example.ru/api/health                # {"ok": true}
```

Для оповещений о падении достаточно бесплатного внешнего мониторинга (например UptimeRobot) на `https://<домен>/api/health`.

## 6. Обновление

```bash
git pull && docker compose --profile prod up -d --build
```

Миграции базы применяются автоматически при старте API и бота.

## Резервная копия базы

```bash
docker compose exec db pg_dump -U gigo gigo | gzip > backup-$(date +%F).sql.gz
```
