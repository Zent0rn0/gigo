"""Бот: открывает Mini App, присылает события по откликам, новые заявки по подпискам, напоминания.

    python -m gigo.bot
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import MenuButtonDefault, MenuButtonWebApp, WebAppInfo

from gigo import config, db
from gigo.bot.handlers import COMMANDS, make_dispatcher
from gigo.bot.loops import notify_once, remind_once, send_outbox_once  # noqa: F401  (тесты импортируют отсюда)
from gigo.migrate import migrate

log = logging.getLogger("gigo.bot")

POLL_EVERY = 15        # секунд между проверками новых заявок
OUTBOX_EVERY = 3       # секунд между проверками очереди событий
REMIND_EVERY = 60
LOOKBACK = timedelta(minutes=10)


async def every(seconds: float, name: str, fn) -> None:
    while True:
        try:
            if n := await fn():
                log.info("%s: %d", name, n)
        except Exception:
            log.exception("ошибка: %s", name)
        await asyncio.sleep(seconds)


async def run() -> None:
    settings = config.load()
    if not settings.bot_token:
        raise SystemExit("Не задан BOT_TOKEN: получите его у @BotFather и впишите в .env")
    await migrate(settings.database_url)
    pool = await db.connect(settings.database_url)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    await bot.set_my_commands(COMMANDS)
    if settings.webapp_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Gigo", web_app=WebAppInfo(url=settings.webapp_url))
        )
    else:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
        log.warning("WEBAPP_URL не задан: кнопок открытия приложения не будет")
    if not settings.admin_ids:
        log.warning("ADMIN_IDS не задан: жалобы на заявки некому разбирать")

    started = datetime.now(timezone.utc)
    tasks = [
        asyncio.create_task(every(OUTBOX_EVERY, "отправлено событий", lambda: send_outbox_once(bot, pool, settings))),
        asyncio.create_task(every(POLL_EVERY, "отправлено по подпискам", lambda: notify_once(
            bot, pool, settings, max(started, datetime.now(timezone.utc) - LOOKBACK)))),
        asyncio.create_task(every(REMIND_EVERY, "напоминаний", lambda: remind_once(pool))),
    ]
    try:
        await make_dispatcher(settings, pool).start_polling(bot)
    finally:
        for task in tasks:
            task.cancel()
        await pool.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
