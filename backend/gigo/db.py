"""Доступ к PostgreSQL через asyncpg."""

import asyncio
import logging
import os

import asyncpg

log = logging.getLogger("gigo.db")

# Сколько ждать один запрос, секунд. Дольше: клиент получает 503, база снимает запрос сама (statement_timeout).
COMMAND_TIMEOUT = float(os.getenv("DB_COMMAND_TIMEOUT", "15"))
POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

# Ошибки «база ещё не поднялась / перезапускается»: на старте их пережидаем.
NOT_READY = (OSError, asyncio.TimeoutError, asyncpg.CannotConnectNowError, asyncpg.PostgresConnectionError,
             asyncpg.TooManyConnectionsError, asyncpg.InterfaceError)


async def connect(url: str, max_size: int = POOL_MAX) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        url, min_size=1, max_size=max_size,
        command_timeout=COMMAND_TIMEOUT,
        timeout=10,  # на установку соединения
        max_inactive_connection_lifetime=300,
        server_settings={
            "application_name": "gigo",
            # запас сверх command_timeout: если клиент не отменил запрос, база снимет его сама
            "statement_timeout": str(int((COMMAND_TIMEOUT + 5) * 1000)),
            # забытая открытой транзакция не держит блокировки вечно
            "idle_in_transaction_session_timeout": "60000",
        },
    )


async def wait_ready(fn, what: str = "база", attempts: int = 30, delay: float = 2.0):
    """Повторяет fn(), пока база не ответит: при старте контейнеров она может подниматься дольше приложения."""
    for i in range(1, attempts + 1):
        try:
            return await fn()
        except NOT_READY as e:
            if i == attempts:
                raise
            log.warning("%s недоступна (%s), попытка %d из %d", what, type(e).__name__, i, attempts)
            await asyncio.sleep(delay)
