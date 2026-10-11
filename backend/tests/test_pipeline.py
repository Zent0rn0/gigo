"""Обработчик целиком на настоящей базе, с подставной моделью вместо ИИ."""

from datetime import datetime, timedelta, timezone

from gigo import db
from gigo.parser.geo import Geocoder, MetroIndex
from gigo.parser.llm import ParseError, from_json
from gigo.parser.pipeline import Processor, pending

NOW = datetime.now(timezone.utc).replace(microsecond=0)

TAGANKA = {"kind": "job", "scam_flags": [], "jobs": [{
    "category": "loader", "title": "Грузчики ×2 · переезд офиса", "workers_needed": 2, "pay_amount": 500,
    "pay_unit": "hour", "pay_timing": "сразу", "date": None, "start_time": None, "duration_hours": 4,
    "metro": ["Таганская"], "address": None, "phone": None, "description": "Переезд офиса на ~4 часа.",
}]}


class FakeLLM:
    def __init__(self):
        self.answers: dict[str, dict] = {}
        self.calls = 0

    async def parse(self, text, sent_at):
        self.calls += 1
        for key, answer in self.answers.items():
            if key in text:
                if answer == "error":
                    raise ParseError("тест")
                return from_json(answer)
        return from_json({"kind": "not_job", "scam_flags": [], "jobs": []})


async def _setup(pool):
    await pool.execute(
        "INSERT INTO metro_stations VALUES ('7.1', 'moscow', 'Таганско-Краснопресненская', '943E90', 'Таганская', "
        "ST_SetSRID(ST_MakePoint(37.6533, 55.7393), 4326)::geography)"
    )
    await pool.execute("INSERT INTO sources (link, chat_id, title) VALUES ('@gruz', -1001, 'Грузчики Москва'), "
                       "('@podr', -1002, 'Подработка')")
    llm = FakeLLM()
    return llm, Processor(pool, llm, await MetroIndex.load(pool, "moscow"), Geocoder(None, pool))


async def _add(pool, chat_id, message_id, text, minutes_ago=5):
    await db.save_messages(pool, [db.RawMessage(chat_id, message_id, 1, NOW - timedelta(minutes=minutes_ago),
                                                None, text, f"https://t.me/x/{message_id}")])
    return await pool.fetchrow("SELECT id, text, sent_at FROM raw_messages WHERE chat_id = $1 AND message_id = $2",
                               chat_id, message_id)


async def test_job_repost_and_flood(pool):
    llm, proc = await _setup(pool)
    llm.answers["Таганская"] = TAGANKA
    post = "СРОЧНО!!! нужны 2 грузчика м.Таганская, переезд офиса ~4ч, 500р/час, оплата сразу. 8 900 123-45-67"

    assert await proc.process(await _add(pool, -1001, 1, post)) == "job"
    job = await pool.fetchrow("SELECT *, ST_Y(location::geometry) AS lat FROM jobs")
    assert job["metro_id"] == "7.1" and abs(job["lat"] - 55.7393) < 1e-6
    assert job["pay_per_hour"] == 500 and job["pay_total"] == 2000 and job["phone"] == "79001234567"
    assert not job["hidden"]

    # тот же текст в другом чате: без ИИ, приклеивается к заказу
    assert await proc.process(await _add(pool, -1002, 7, post + " 🔥")) == "duplicate"
    assert llm.calls == 1
    assert await pool.fetchval("SELECT count(*) FROM job_messages WHERE job_id = $1", job["id"]) == 2

    # флуд даже не доходит до ИИ
    assert await proc.process(await _add(pool, -1001, 2, "Всем привет, как дела?")) == "not_job"
    assert llm.calls == 1


async def test_same_phone_merges_and_scam_hidden(pool):
    llm, proc = await _setup(pool)
    llm.answers["переезд"] = TAGANKA
    await proc.process(await _add(pool, -1001, 1, "Нужны грузчики на переезд, Таганская, 500р/ч, тел 89001234567"))
    status = await proc.process(await _add(pool, -1002, 2, "Грузчики на переезд офиса!!! 500 в час, +7 900 123 45 67"))
    assert status == "duplicate"
    assert await pool.fetchval("SELECT count(*) FROM jobs") == 1

    llm.answers["курьер"] = {**TAGANKA, "jobs": [{**TAGANKA["jobs"][0], "category": "courier", "title": "Курьер"}]}
    await proc.process(await _add(pool, -1001, 3, "Работа курьером, высокий доход от 150 000 в неделю, оплата сразу"))
    hidden = await pool.fetchrow("SELECT hidden, scam_flags FROM jobs WHERE category = 'courier'")
    assert hidden["hidden"] and "drugs" in hidden["scam_flags"]


async def test_edit_replaces_job_and_errors_retry(pool):
    llm, proc = await _setup(pool)
    llm.answers["переезд"] = TAGANKA
    msg = await _add(pool, -1001, 1, "Нужны грузчики на переезд, 500р/ч")
    await proc.process(msg)
    first = await pool.fetchval("SELECT id FROM jobs")

    msg = await _add(pool, -1001, 1, "Нужны грузчики на переезд, 700р/ч")  # правка того же сообщения
    assert [r["id"] for r in await pending(pool, 10, timedelta(days=7))] == [msg["id"]]
    await proc.process(msg)
    assert await pool.fetchval("SELECT count(*) FROM jobs") == 1
    assert await pool.fetchval("SELECT id FROM jobs") != first

    llm.answers["сломалось"] = "error"
    broken = await _add(pool, -1001, 9, "Нужны люди, сломалось, оплата 500")
    for _ in range(3):
        try:
            await proc.process(broken)
        except ParseError:
            pass
    assert await pool.fetchval("SELECT parse_status FROM raw_messages WHERE id = $1", broken["id"]) == "error"
