"""Демо-данные: заказчики с заявками и отзывами, чтобы посмотреть приложение до первых настоящих.

    python -m gigo.demo          # добавить
    python -m gigo.demo --clear  # убрать
"""

import argparse
import asyncio
from datetime import datetime, timedelta

from gigo import config, db, rules
from gigo.migrate import migrate

# Демо-пользователи живут в этом диапазоне id: настоящие id Telegram сюда не попадают на практике,
# а --clear удаляет всё в нём одним запросом.
DEMO_IDS = (9_000_000_000_000, 9_000_000_000_999)

# Станции на случай, если справочник метро ещё не загружен.
STATIONS = [
    ("demo.taganskaya", "Таганско-Краснопресненская", "943E90", "Таганская", 55.7393, 37.6533),
    ("demo.kurskaya", "Кольцевая", "915133", "Курская", 55.7586, 37.6611),
    ("demo.vdnh", "Калужско-Рижская", "F07E24", "ВДНХ", 55.8196, 37.6411),
    ("demo.yugo", "Сокольническая", "EF161E", "Юго-Западная", 55.6634, 37.4831),
    ("demo.lyublino", "Люблинско-Дмитровская", "BED12C", "Люблино", 55.6762, 37.7617),
    ("demo.belorusskaya", "Замоскворецкая", "4FB04F", "Белорусская", 55.7772, 37.5822),
]

EMPLOYERS = [
    (DEMO_IDS[0] + 1, "Ольга", "Логистическая компания, переезды офисов"),
    (DEMO_IDS[0] + 2, "Склад «Восток»", "Распределительный склад в Люблино"),
    (DEMO_IDS[0] + 3, "Артём", "Организую выставки и мероприятия"),
]
WORKERS = [
    (DEMO_IDS[0] + 101, "Иван", "Грузчик, опыт 3 года"),
    (DEMO_IDS[0] + 102, "Мария", "Уборка, промо, склад"),
]

# (заказчик, минут назад, категория, заголовок, людей, сумма, единица, часов, когда платят, станция,
#  через сколько часов старт, описание)
JOBS = [
    (1, 12, "loader", "Грузчики на переезд офиса", 2, 500, "hour", 4, "сразу", "Таганская", 2,
     "Переезд офиса, мебель и коробки. Лифт есть."),
    (2, 25, "warehouse", "Комплектовщики на склад", 5, 3200, "shift", 12, "в конце смены", "Люблино", 20,
     "Ночная смена 20:00–08:00, сборка заказов. Паспорт РФ."),
    (1, 40, "courier", "Пеший курьер · документы", 1, 450, "hour", 6, "раз в неделю", "Курская", None,
     "Доставка документов по центру, проездной компенсируют."),
    (3, 55, "promo", "Промоутер у метро", 2, 350, "hour", 5, "сразу", "ВДНХ", 3,
     "Раздача листовок у выхода из метро."),
    (1, 80, "cleaning", "Уборка после ремонта", 2, 4000, "task", None, "сразу", "Юго-Западная", 24,
     "Квартира 2 комнаты, инвентарь дадим."),
    (3, 95, "event", "Монтажники на выставку", 6, 2800, "shift", 10, "сразу", "ВДНХ", 22,
     "Сборка стендов на выставке, нужны перчатки."),
    (2, 130, "kitchen", "Посудомойщица в кафе", 1, 300, "hour", 12, "каждый день", "Белорусская", None,
     "Смена 10:00–22:00, питание бесплатно, нужна медкнижка."),
    (2, 160, "loader", "Разгрузка фуры · 20 т", 4, 2500, "task", 3, "сразу", "Люблино", 1,
     "Мешки по 25 кг, разгрузка на склад."),
]


async def add(pool) -> int:
    for sid, line, color, name, lat, lng in STATIONS:
        await pool.execute(
            """INSERT INTO metro_stations (id, city, line, line_color, name, location)
               SELECT $1, 'moscow', $2, $3, $4, ST_SetSRID(ST_MakePoint($6, $5), 4326)::geography
               WHERE NOT EXISTS (SELECT 1 FROM metro_stations WHERE name = $4)""",
            sid, line, color, name, lat, lng,
        )
    for uid, name, about in EMPLOYERS:
        await pool.execute("INSERT INTO users (tg_id, first_name, role, about) VALUES ($1, $2, 'employer', $3) "
                           "ON CONFLICT DO NOTHING", uid, name, about)
    for uid, name, about in WORKERS:
        await pool.execute("INSERT INTO users (tg_id, first_name, role, about) VALUES ($1, $2, 'worker', $3) "
                           "ON CONFLICT DO NOTHING", uid, name, about)

    now = datetime.now(rules.MSK).replace(second=0, microsecond=0)
    n = 0
    for emp, ago, cat, title, workers, amount, unit, hours, timing, station, start_in, desc in JOBS:
        metro = await pool.fetchrow(
            "SELECT id, location FROM metro_stations WHERE name = $1 ORDER BY id LIMIT 1", station
        )
        created = now - timedelta(minutes=ago)
        start = (now + timedelta(hours=start_in)).replace(minute=0) if start_in is not None else None
        per_hour, estimated = rules.pay_per_hour(amount, unit, hours)
        await pool.execute(
            """INSERT INTO jobs (employer_id, category, title, workers_needed, pay_amount, pay_unit, pay_per_hour,
                                 pay_estimated, pay_total, pay_timing, starts_on, starts_at, duration_hours, metro_id,
                                 location, description, created_at, updated_at, expires_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $17, $18)""",
            DEMO_IDS[0] + emp, cat, title, workers, amount, unit, per_hour, estimated,
            rules.pay_total(amount, unit, hours), timing, start.date() if start else None, start, hours,
            metro["id"], metro["location"], desc, created, rules.expires_at(created, start and start.date(), start),
        )
        n += 1

    # Прошлая выполненная заявка с отзывами, чтобы у заказчиков был рейтинг.
    for emp, worker, title, rating_e, rating_w, text_e, text_w in [
        (1, 101, "Переезд квартиры", 5, 5, "Всё чётко, заплатили сразу", "Работал быстро и аккуратно"),
        (2, 102, "Сборка заказов на складе", 4, 5, "Нормально, но смену задержали на час", "Отличная работа"),
        (3, 101, "Монтаж сцены", 5, 4, "Хороший заказчик", "Опоздал на 15 минут, в остальном отлично"),
    ]:
        job_id = await pool.fetchval(
            """INSERT INTO jobs (employer_id, status, category, title, pay_amount, pay_unit, pay_per_hour,
                                 created_at, expires_at)
               VALUES ($1, 'closed', 'loader', $2, 500, 'hour', 500,
                       now() - interval '10 days', now() - interval '9 days') RETURNING id""",
            DEMO_IDS[0] + emp, title,
        )
        await pool.execute("INSERT INTO responses (job_id, worker_id, status) VALUES ($1, $2, 'accepted')",
                           job_id, DEMO_IDS[0] + worker)
        await pool.execute(
            "INSERT INTO reviews (job_id, author_id, target_id, rating, text) VALUES ($1, $2, $3, $4, $5), "
            "($1, $3, $2, $6, $7)",
            job_id, DEMO_IDS[0] + worker, DEMO_IDS[0] + emp, rating_e, text_e, rating_w, text_w,
        )
    return n


async def run(clear: bool) -> None:
    settings = config.load()
    await migrate(settings.database_url)
    pool = await db.connect(settings.database_url)
    if clear:
        n = await pool.fetchval(
            "WITH d AS (DELETE FROM jobs WHERE employer_id BETWEEN $1 AND $2 AND status = 'open' RETURNING 1) "
            "SELECT count(*) FROM d", *DEMO_IDS)
        await pool.execute("DELETE FROM users WHERE tg_id BETWEEN $1 AND $2", *DEMO_IDS)
        await pool.execute("DELETE FROM metro_stations WHERE id LIKE 'demo.%' "
                           "AND NOT EXISTS (SELECT 1 FROM jobs WHERE metro_id = metro_stations.id)")
        print(f"Удалено демо-заявок: {n}")
    else:
        if await pool.fetchval("SELECT count(*) FROM users WHERE tg_id BETWEEN $1 AND $2", *DEMO_IDS):
            print("Демо-данные уже есть. Убрать: python -m gigo.demo --clear")
        else:
            print(f"Добавлено демо-заявок: {await add(pool)}")
    await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m gigo.demo")
    parser.add_argument("--clear", action="store_true")
    asyncio.run(run(parser.parse_args().clear))


if __name__ == "__main__":
    main()
