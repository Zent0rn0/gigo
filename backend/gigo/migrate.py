"""Применяет SQL-миграции из gigo/migrations по порядку, каждую один раз.

    python -m gigo.migrate
"""

import asyncio
from pathlib import Path

import asyncpg

from gigo import config

MIGRATIONS = Path(__file__).parent / "migrations"


async def migrate(url: str) -> list[str]:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        # Защита от двух одновременных запусков (api и бот стартуют вместе).
        await conn.execute("SELECT pg_advisory_lock(727274)")
        done = {r["name"] for r in await conn.fetch("SELECT name FROM schema_migrations")}
        applied = []
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute("INSERT INTO schema_migrations (name) VALUES ($1)", path.name)
            applied.append(path.name)
        return applied
    finally:
        await conn.close()


def main() -> None:
    applied = asyncio.run(migrate(config.load().database_url))
    print("Применены миграции: " + ", ".join(applied) if applied else "База в актуальном состоянии.")


if __name__ == "__main__":
    main()
