# Gigo · Подработка на карте

Telegram Mini App: заказы на подработку из чатов «Грузчики Москва», «Подработка» и других собраны в одну ленту и на карту.

Чаты Telegram → **сборщик** (Telethon) → `raw_messages` → **разбор ИИ** → `jobs` (PostGIS) → API → Mini App и бот.

## Что готово

- [x] База: PostgreSQL 16 + PostGIS, схема в `db/init/001_schema.sql`
- [x] Сборщик: вступает в чаты из `sources.txt`, тянет историю и читает новые сообщения в реальном времени
- [x] Справочник метро с координатами (hh.ru)
- [ ] Разбор объявлений ИИ, склейка дублей, метро → точка (этап 2)
- [ ] API и Mini App: лента, карточка, фильтры (этап 3)
- [ ] Карта (этап 4)
- [ ] Бот с push-подписками (этап 5)
- [ ] Деплой (этап 6)

## Запуск на своей машине

Нужны Docker Desktop и Python 3.12.

```bash
cp .env.example .env              # вписать TG_API_ID и TG_API_HASH аккаунта-сборщика
docker compose up -d db           # база в Docker, схема создаётся сама

cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python -m gigo.metro              # станции метро Москвы
python -m gigo.collector login    # вход в аккаунт-сборщик: телефон, код из Telegram, пароль 2FA
```

Дальше впишите чаты в `sources.txt` (по одному на строку: `t.me/имя`, `@имя` или `t.me/+приглашение`) и:

```bash
python -m gigo.collector join     # вступит в следующие 5 чатов с паузами 2–5 минут
python -m gigo.collector run      # подтянет историю за 7 дней и будет слушать новые сообщения
python -m gigo.collector stats    # сколько собрано по каждому чату
```

`join` за раз вступает только в `JOIN_BATCH` чатов: так меньше риск бана. Запускайте его раз в час-два, пока все чаты не будут пройдены; `run` сам подхватит новые чаты в течение 10 минут.

Когда наберётся 3–7 дней сообщений, `python -m gigo.collector export` сохранит 200 случайных в `data/sample.jsonl`: на них проверяем парсер на этапе 2.

## Безопасность аккаунта

- Аккаунт-сборщик отдельный, на отдельной SIM. Он только читает: ничего не пишет и не ставит реакций.
- Файл сессии `data/collector.session` даёт полный доступ к аккаунту. Он в `.gitignore`, никому его не отправляйте, как и `.env`.

## Тесты

```bash
cd backend && pytest     # тесты базы пропускаются, если она не запущена
```
