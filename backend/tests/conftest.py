"""Общие фикстуры. Тесты с базой пропускаются, если она не запущена (docker compose up -d db)."""

import os

import asyncpg
import pytest

from gigo import db
from gigo.migrate import migrate

# Отдельная база, чтобы тесты не трогали данные разработки.
URL = os.getenv("TEST_DATABASE_URL", "postgresql://gigo:gigo@localhost:5432/gigo_test")


async def _ensure_database(url: str) -> None:
    admin_url, name = url.rsplit("/", 1)
    conn = await asyncpg.connect(f"{admin_url}/postgres")
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture
async def pool(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    try:
        await _ensure_database(URL)
        await migrate(URL)
        pool = await db.connect(URL)
    except (OSError, asyncpg.PostgresError) as e:
        pytest.skip(f"база недоступна: {e}")
    await pool.execute("TRUNCATE users, metro_stations, geocode_cache RESTART IDENTITY CASCADE")
    yield pool
    await pool.close()
