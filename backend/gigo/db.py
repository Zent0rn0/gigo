"""Доступ к PostgreSQL через asyncpg."""

import asyncpg


async def connect(url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(url, min_size=1, max_size=5)
