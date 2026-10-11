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
| `TG_API_ID`, `TG_API_HASH` | аккаунт-сборщик |
| `BOT_TOKEN` | токен бота |
| `ANTHROPIC_API_KEY` или `YANDEX_GPT_API_KEY` + `YANDEX_FOLDER_ID` + `LLM_PROVIDER=yandex` | ИИ |
| `YANDEX_GEOCODER_KEY`, `VITE_YANDEX_MAPS_KEY` | карты |
| `DOMAIN` | `gigo.example.ru` |
| `WEBAPP_URL` | `https://gigo.example.ru` |
| `POSTGRES_PASSWORD` | длинный случайный пароль |
| `DEV_AUTH` | `0` |

В `sources.txt` впишите чаты.

## 3. Запуск

```bash
docker compose --profile prod build
docker compose up -d db
docker compose --profile prod run --rm api python -m gigo.migrate
docker compose --profile prod run --rm api python -m gigo.metro
docker compose --profile prod run --rm collector python -m gigo.collector login   # код придёт в Telegram
docker compose --profile prod run --rm collector python -m gigo.collector join
docker compose --profile prod up -d
```

Если сессия сборщика уже создана на своём компьютере, можно вместо `login` скопировать `data/collector.session` на сервер в папку `data/`.

Вступать в оставшиеся чаты постепенно (раз в час-два):

```bash
docker compose --profile prod run --rm collector python -m gigo.collector join
```

Чтобы делать это автоматически, добавьте в `crontab -e`:

```
0 */2 * * * cd /root/gigo && docker compose --profile prod run --rm collector python -m gigo.collector join >> /root/gigo/data/join.log 2>&1
```

## 4. Mini App в боте

В @BotFather: `/mybots` → бот → Bot Settings → Configure Mini App → Enable Mini App → URL `https://gigo.example.ru`.
Кнопку меню «Заказы» бот ставит сам при старте, если задан `WEBAPP_URL`.

## 5. Наблюдение

```bash
docker compose --profile prod ps                       # все сервисы должны быть Up, api — healthy
docker compose --profile prod logs -f parser           # «разобрано 50: job 12, not_job 30, …»
docker compose --profile prod run --rm collector python -m gigo.collector stats
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
