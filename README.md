# Gigo · Подработка на карте

Telegram Mini App: заказы на подработку из чатов «Грузчики Москва», «Подработка» и других собраны в одну ленту, на карту и в push-уведомления.

```
Чаты Telegram → сборщик (Telethon) → raw_messages → обработчик (ИИ) → jobs (PostGIS) → API → Mini App
                                                                                     └→ бот: push по подпискам
```

| Часть | Где | Запуск |
|---|---|---|
| Сборщик | `backend/gigo/collector` | `python -m gigo.collector run` |
| Обработчик (разбор ИИ, дубли, метро → точка) | `backend/gigo/parser` | `python -m gigo.parser run` |
| API | `backend/gigo/api` | `uvicorn gigo.api.app:app` |
| Бот | `backend/gigo/bot` | `python -m gigo.bot` |
| Mini App (React + Vite + Яндекс Карты) | `frontend` | `npm run dev` |
| База (PostgreSQL 16 + PostGIS) | `backend/gigo/migrations` | `docker compose up -d db` |

Контракт API: [docs/api.md](docs/api.md). Как выложить на сервер: [docs/deploy.md](docs/deploy.md).

## Что нужно подготовить

1. **Отдельный аккаунт Telegram** на отдельной SIM и его `api_id` / `api_hash` с my.telegram.org.
2. **Бот** от @BotFather: токен.
3. **Ключ ИИ**: Claude (console.anthropic.com) или YandexGPT (Yandex Cloud: API-ключ и id каталога).
4. **Ключи Яндекс Карт** на developer.tech.yandex.ru: JavaScript API (для карты) и HTTP Геокодер (для адресов).
5. **Список чатов-источников** в `sources.txt`.
6. Для запуска в Telegram: **сервер и домен** (см. docs/deploy.md).

Всё вписывается в `.env` (образец в `.env.example`). Ключи и коды не пересылаем в чат.

## Запуск на своей машине

Нужны Docker Desktop, Python 3.12 и Node 22.

```bash
cp .env.example .env              # заполнить ключи
docker compose up -d db           # база

cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m gigo.migrate            # таблицы
python -m gigo.metro              # станции метро Москвы с координатами (hh.ru)
```

### 1. Копим сообщения

```bash
python -m gigo.collector login    # вход в аккаунт-сборщик: телефон, код из Telegram, пароль 2FA
python -m gigo.collector join     # вступит в следующие 5 чатов из sources.txt с паузами 2–5 минут
python -m gigo.collector run      # подтянет историю за 7 дней и будет слушать новые сообщения
python -m gigo.collector stats    # сколько собрано по каждому чату
```

`join` за раз вступает только в `JOIN_BATCH` чатов, чтобы не словить бан. Запускайте его раз в час-два, пока все чаты не пройдены; работающий `run` подхватит новые чаты сам.

### 2. Проверяем разбор на 200 сообщениях

```bash
python -m gigo.parser test tests/fixtures/sample_posts.jsonl   # 12 типичных объявлений, сразу
python -m gigo.collector export                                # 200 случайных настоящих в data/sample.jsonl
python -m gigo.parser test ../data/sample.jsonl                # отчёт в data/parse_report.md
```

Отчёт показывает, как ИИ понял каждое сообщение: категория, ₽/час, метро, время, признаки мошенничества. Если что-то разобрано не так, правим промпт в `gigo/parser/llm.py` и повторяем.

### 3. Запускаем всё

```bash
python -m gigo.parser run                               # разбирает новые сообщения в заказы
DEV_AUTH=1 uvicorn gigo.api.app:app --reload --port 8000
python -m gigo.bot                                      # нужен BOT_TOKEN

cd ../frontend && npm install && npm run dev            # http://localhost:5173
```

`DEV_AUTH=1` пускает в API без подписи Telegram, только для разработки. Посмотреть интерфейс до появления настоящих заказов: `python -m gigo.demo` добавит 8 демо-заказов, `python -m gigo.demo --clear` уберёт.

## Как это работает

**Сборщик** только читает: не пишет, не ставит реакций. Сохраняет текст, ссылку на оригинал и время; правка сообщения отправляет его на повторный разбор.

**Обработчик** на каждое сообщение:
1. Отсеивает флуд правилами, без ИИ (`gigo/parser/rules.py`).
2. Точный репост уже известного объявления (тот же текст в другом чате) приклеивает к заказу, без ИИ.
3. Отправляет текст модели: ответ строго по JSON-схеме, несколько работ в одном посте дают несколько карточек.
4. Приводит оплату к ₽/час (смена без длительности считается за 8 часов и помечается «≈»), находит станцию метро, геокодирует адрес, вычисляет, когда заказ просрочится.
5. Склеивает дубли по телефону и категории.
6. Признаки мошенничества и вербовки (правила + ИИ) скрывают заказ из ленты.

По умолчанию модель `claude-haiku-5-5`; переключение на YandexGPT: `LLM_PROVIDER=yandex`.

**Бот** раз в 15 секунд сверяет новые заказы с подписками и присылает каждый подходящий заказ один раз.

## Тесты

```bash
cd backend && pytest          # тесты с базой создают отдельную базу gigo_test и пропускаются, если Docker не запущен
cd frontend && npm run build  # проверка типов и сборка
```

## Безопасность

- Файл `data/collector.session` даёт полный доступ к аккаунту-сборщику. Он в `.gitignore`, как и `.env`.
- Вход в API только с подписанными данными Telegram (`initData`), подпись проверяется токеном бота.
- Путь к заказчику: телефон из исходного объявления и кнопка «Открыть пост», своей базы телефонов не собираем.
