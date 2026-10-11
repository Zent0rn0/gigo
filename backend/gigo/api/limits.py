"""Ограничения частоты действий."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimiter:
    """Скользящее окно в памяти процесса: не больше limit событий за window секунд на ключ."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self.hits: dict[int, deque] = defaultdict(deque)

    def hit(self, key: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self.hits[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self.hits) > 50_000:  # не копим память на тех, кто давно ушёл
            for k in [k for k, v in self.hits.items() if not v or v[-1] <= now - self.window]:
                del self.hits[k]
        return True


async def check_recent(conn, sql: str, user_id: int, limit: int, message: str) -> None:
    """Лимит по базе (переживает перезапуск): sql считает действия пользователя $1 за период."""
    if await conn.fetchval(sql, user_id) >= limit:
        raise HTTPException(429, message)
