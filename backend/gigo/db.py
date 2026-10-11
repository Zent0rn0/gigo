"""Доступ к PostgreSQL через asyncpg."""

from dataclasses import dataclass
from datetime import datetime

import asyncpg


async def connect(url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(url, min_size=1, max_size=5)


@dataclass(frozen=True)
class RawMessage:
    chat_id: int
    message_id: int
    sender_id: int | None
    sent_at: datetime
    edited_at: datetime | None
    text: str
    link: str | None


# Правка текста сбрасывает processed_at: парсер разберёт сообщение заново.
_UPSERT_MESSAGE = """
INSERT INTO raw_messages (chat_id, message_id, sender_id, sent_at, edited_at, text, link)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (chat_id, message_id) DO UPDATE SET
    edited_at = EXCLUDED.edited_at,
    text = EXCLUDED.text,
    link = COALESCE(EXCLUDED.link, raw_messages.link),
    processed_at = CASE WHEN raw_messages.text IS DISTINCT FROM EXCLUDED.text
                        THEN NULL ELSE raw_messages.processed_at END,
    parse_status = CASE WHEN raw_messages.text IS DISTINCT FROM EXCLUDED.text
                        THEN NULL ELSE raw_messages.parse_status END
"""


def _row(m: RawMessage) -> tuple:
    return (m.chat_id, m.message_id, m.sender_id, m.sent_at, m.edited_at, m.text, m.link)


async def save_messages(pool: asyncpg.Pool, messages: list[RawMessage]) -> None:
    if messages:
        await pool.executemany(_UPSERT_MESSAGE, [_row(m) for m in messages])


async def last_message_id(pool: asyncpg.Pool, chat_id: int) -> int | None:
    return await pool.fetchval("SELECT max(message_id) FROM raw_messages WHERE chat_id = $1", chat_id)


async def upsert_source_links(pool: asyncpg.Pool, links: list[str]) -> int:
    """Добавляет новые ссылки из sources.txt, возвращает сколько добавлено."""
    rows = await pool.fetch(
        "INSERT INTO sources (link) SELECT unnest($1::text[]) ON CONFLICT (link) DO NOTHING RETURNING id",
        links,
    )
    return len(rows)


async def pending_sources(pool: asyncpg.Pool, limit: int) -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT id, link FROM sources WHERE enabled AND chat_id IS NULL ORDER BY id LIMIT $1", limit
    )


async def joined_sources(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT id, link, chat_id, username, title FROM sources WHERE enabled AND chat_id IS NOT NULL ORDER BY id"
    )


async def mark_joined(pool: asyncpg.Pool, source_id: int, chat_id: int, username: str | None, title: str) -> None:
    await pool.execute(
        """UPDATE sources SET chat_id = $2, username = $3, title = $4,
                  joined_at = coalesce(joined_at, now()), last_error = NULL
           WHERE id = $1""",
        source_id, chat_id, username, title,
    )


async def mark_error(pool: asyncpg.Pool, source_id: int, error: str, disable: bool = False) -> None:
    await pool.execute(
        "UPDATE sources SET last_error = $2, enabled = enabled AND NOT $3 WHERE id = $1",
        source_id, error[:500], disable,
    )
