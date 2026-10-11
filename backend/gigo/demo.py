"""Демо-заказы, чтобы посмотреть приложение до того, как накопятся настоящие.

    python -m gigo.demo          # добавить
    python -m gigo.demo --clear  # убрать
"""

import argparse
import asyncio
from datetime import datetime, timedelta

from gigo import config, db
from gigo.migrate import migrate
from gigo.parser.rules import MSK, pay_per_hour, pay_total

DEMO_HASH = "demo"

# Станции на случай, если справочник метро ещё не загружен.
STATIONS = [
    ("demo.taganskaya", "Таганско-Краснопресненская", "943E90", "Таганская", 55.7393, 37.6533),
    ("demo.kurskaya", "Кольцевая", "915133", "Курская", 55.7586, 37.6611),
    ("demo.vdnh", "Калужско-Рижская", "F07E24", "ВДНХ", 55.8196, 37.6411),
    ("demo.yugo", "Сокольническая", "EF161E", "Юго-Западная", 55.6634, 37.4831),
    ("demo.lyublino", "Люблинско-Дмитровская", "BED12C", "Люблино", 55.6762, 37.7617),
    ("demo.belorusskaya", "Замоскворецкая", "4FB04F", "Белорусская", 55.7772, 37.5822),
]

# (минут назад, категория, заголовок, людей, сумма, единица, часов, когда платят, станция, через сколько часов старт, описание, телефон)
JOBS = [
    (12, "loader", "Грузчики ×2 · переезд офиса", 2, 500, "hour", 4, "сразу", "Таганская", 2,
     "Переезд офиса, мебель и коробки. Лифт есть.", "79001234567"),
    (25, "warehouse", "Комплектовщики на склад", 5, 3200, "shift", 12, "в конце смены", "Люблино", 20,
     "Ночная смена 20:00–08:00, сборка заказов. Паспорт РФ.", None),
    (40, "courier", "Пеший курьер · документы", 1, 450, "hour", 6, "раз в неделю", "Курская", None,
     "Доставка документов по центру, проездной компенсируют.", "79157654321"),
    (55, "promo", "Промоутер у метро", 2, 350, "hour", 5, "сразу", "ВДНХ", 3,
     "Раздача листовок у выхода из метро.", None),
    (80, "cleaning", "Уборка после ремонта", 2, 4000, "task", None, "сразу", "Юго-Западная", 24,
     "Квартира 2 комнаты, инвентарь дадим.", "79261112233"),
    (95, "event", "Монтажники на выставку", 6, 2800, "shift", 10, "сразу", "ВДНХ", 22,
     "Сборка стендов на выставке, нужны перчатки.", None),
    (130, "kitchen", "Посудомойщица в кафе", 1, 300, "hour", 12, "каждый день", "Белорусская", None,
     "Смена 10:00–22:00, питание бесплатно, нужна медкнижка.", None),
    (160, "loader", "Разгрузка фуры · 20 т", 4, 2500, "task", 3, "сразу", "Люблино", 1,
     "Мешки по 25 кг, разгрузка на склад.", "79005553535"),
]


async def add(pool) -> int:
    for sid, line, color, name, lat, lng in STATIONS:
        await pool.execute(
            """INSERT INTO metro_stations (id, city, line, line_color, name, location)
               SELECT $1, 'moscow', $2, $3, $4, ST_SetSRID(ST_MakePoint($6, $5), 4326)::geography
               WHERE NOT EXISTS (SELECT 1 FROM metro_stations WHERE name = $4)""",
            sid, line, color, name, lat, lng,
        )
    now = datetime.now(MSK).replace(second=0, microsecond=0)
    n = 0
    for ago, cat, title, workers, amount, unit, hours, timing, station, start_in, desc, phone in JOBS:
        metro = await pool.fetchrow(
            "SELECT id, location FROM metro_stations WHERE name = $1 ORDER BY id LIMIT 1", station
        )
        seen = now - timedelta(minutes=ago)
        start = (now + timedelta(hours=start_in)).replace(minute=0) if start_in is not None else None
        per_hour, estimated = pay_per_hour(amount, unit, hours)
        await pool.execute(
            """INSERT INTO jobs (category, title, workers_needed, pay_amount, pay_unit, pay_per_hour, pay_estimated,
                                 pay_total, pay_timing, starts_on, starts_at, duration_hours, metro_id, location,
                                 description, phone, text_hash, first_seen_at, last_seen_at, expires_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $18, $19)""",
            cat, title, workers, amount, unit, per_hour, estimated, pay_total(amount, unit, hours), timing,
            start.date() if start else None, start, hours, metro["id"], metro["location"], desc, phone,
            DEMO_HASH, seen, (start + timedelta(hours=1)) if start else seen + timedelta(hours=24),
        )
        n += 1
    return n


async def run(clear: bool) -> None:
    settings = config.load()
    await migrate(settings.database_url)
    pool = await db.connect(settings.database_url)
    if clear:
        n = await pool.fetchval("WITH d AS (DELETE FROM jobs WHERE text_hash = $1 RETURNING 1) SELECT count(*) FROM d",
                                DEMO_HASH)
        await pool.execute("DELETE FROM metro_stations WHERE id LIKE 'demo.%' "
                           "AND NOT EXISTS (SELECT 1 FROM jobs WHERE metro_id = metro_stations.id)")
        print(f"Удалено демо-заказов: {n}")
    else:
        print(f"Добавлено демо-заказов: {await add(pool)}")
    await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m gigo.demo")
    parser.add_argument("--clear", action="store_true")
    asyncio.run(run(parser.parse_args().clear))


if __name__ == "__main__":
    main()
