"""Тесты с настоящей базой. Нужен запущенный `docker compose up -d db` (или TEST_DATABASE_URL)."""

from datetime import datetime, timezone

from gigo import db


def _raw(text, message_id=1):
    return db.RawMessage(-1001, message_id, 42, datetime(2026, 10, 11, tzinfo=timezone.utc), None, text, None)


async def test_edit_resets_processing(pool):
    await db.save_messages(pool, [_raw("нужны грузчики 500р/ч")])
    await pool.execute("UPDATE raw_messages SET processed_at = now(), parse_status = 'job'")

    await db.save_messages(pool, [_raw("нужны грузчики 500р/ч")])  # повтор без изменений
    assert await pool.fetchval("SELECT parse_status FROM raw_messages") == "job"

    await db.save_messages(pool, [_raw("нужны грузчики 700р/ч")])  # правка текста
    row = await pool.fetchrow("SELECT text, processed_at, parse_status FROM raw_messages")
    assert row["text"] == "нужны грузчики 700р/ч"
    assert row["processed_at"] is None and row["parse_status"] is None
    assert await db.last_message_id(pool, -1001) == 1


async def test_sources_flow(pool):
    assert await db.upsert_source_links(pool, ["@a_chat", "+hash"]) == 2
    assert await db.upsert_source_links(pool, ["@a_chat", "@b_chat"]) == 1
    pending = await db.pending_sources(pool, 10)
    assert [p["link"] for p in pending] == ["@a_chat", "+hash", "@b_chat"]

    await db.mark_joined(pool, pending[0]["id"], -1001, "a_chat", "Чат А")
    await db.mark_error(pool, pending[1]["id"], "InviteHashExpiredError", disable=True)
    assert [p["link"] for p in await db.pending_sources(pool, 10)] == ["@b_chat"]
    assert [s["chat_id"] for s in await db.joined_sources(pool)] == [-1001]


async def test_postgis_ready(pool):
    km = await pool.fetchval("""
        SELECT ST_Distance(ST_MakePoint(37.6533, 55.7393)::geography,
                           ST_MakePoint(37.6176, 55.7558)::geography) / 1000""")
    assert 2 < km < 3  # Таганская — Красная площадь
