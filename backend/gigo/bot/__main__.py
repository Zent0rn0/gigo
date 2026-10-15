"""Бот: открывает Mini App, присылает события по откликам, новые заявки по подпискам, напоминания.

    python -m gigo.bot
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import MenuButtonDefault, MenuButtonWebApp, WebAppInfo

from gigo import config, db
from gigo.bot import look
from gigo.bot.handlers import COMMANDS, make_dispatcher
from gigo.bot.loops import notify_once, remind_once, send_outbox_once  # noqa: F401  (тесты импортируют отсюда)
from gigo.migrate import migrate

log = logging.getLogger("gigo.bot")

POLL_EVERY = 15        # секунд между проверками новых заявок
OUTBOX_EVERY = 3       # секунд между проверками очереди событий
REMIND_EVERY = 60
LOOKBACK = timedelta(minutes=10)
TASK_TIMEOUT = 300   # фоновая задача дольше этого считается зависшей
MAX_BACKOFF = 120


async def every(seconds: float, name: str, fn) -> None:
    """Повторяет fn каждые seconds секунд. Ошибка не останавливает цикл: при сбоях паузы растут до MAX_BACKOFF,
    полный traceback пишется один раз, а не каждые 3 секунды."""
    fails = 0
    while True:
        try:
            if n := await asyncio.wait_for(fn(), TASK_TIMEOUT):
                log.info("%s: %d", name, n)
            if fails:
                log.info("%s: снова работает после %d сбоев", name, fails)
            fails = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            fails += 1
            if fails == 1:
                log.exception("ошибка: %s", name)
            else:
                log.warning("ошибка: %s (подряд %d): %r", name, fails, e)
        await asyncio.sleep(min(seconds * 2 ** min(fails, 10), MAX_BACKOFF) if fails else seconds)


async def retry(what: str, fn, attempts: int = 30):
    """Запуск: ждём базу и Telegram (после перезагрузки сервера они поднимаются не сразу)."""
    for i in range(1, attempts + 1):
        try:
            return await fn()
        except TelegramUnauthorizedError:
            raise SystemExit("Telegram не принял BOT_TOKEN: проверьте токен в .env (его выдаёт @BotFather)")
        except Exception as e:
            if i == attempts:
                raise
            wait = min(2 * i, 30)
            log.warning("%s: не получилось (%r), пробую снова через %d с", what, e, wait)
            await asyncio.sleep(wait)


async def setup(bot: Bot, settings) -> None:
    """Меню и кнопка приложения. Не критично: если Telegram сейчас не ответил, бот всё равно работает."""
    try:
        if sets := [s for s in os.getenv("CUSTOM_EMOJI_SETS", "").replace(" ", "").split(",") if s]:
            n = await look.load_custom_emoji(bot, sets)
            log.info("премиум-эмодзи: %d замен из наборов %s", n, ", ".join(sets))
        await bot.set_my_commands(COMMANDS)
        if settings.webapp_url:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="Gigo", web_app=WebAppInfo(url=settings.webapp_url))
            )
        else:
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            log.warning("WEBAPP_URL не задан: кнопок открытия приложения не будет")
    except Exception as e:
        log.warning("не удалось настроить меню бота, продолжаю без этого: %r", e)


async def run() -> None:
    settings = config.load()
    if not settings.bot_token:
        raise SystemExit("Не задан BOT_TOKEN: получите его у @BotFather и впишите в .env")
    await retry("миграции базы", lambda: migrate(settings.database_url))
    pool = await retry("подключение к базе", lambda: db.connect(settings.database_url))
    session = None
    # С российских серверов api.telegram.org недоступен: бот ходит через ретранслятор за рубежом (deploy/relay-setup.sh).
    if api_url := os.getenv("TELEGRAM_API_URL", "").strip().rstrip("/"):
        session = AiohttpSession(api=TelegramAPIServer.from_base(api_url))
        log.info("Telegram API через %s", api_url)
    bot = Bot(settings.bot_token, session=session, default=DefaultBotProperties(parse_mode="HTML"))
    bot.session.middleware(look.PrettyMiddleware())
    bot.session.middleware(look.PlainFallbackMiddleware())
    tasks = []
    try:
        me = await retry("связь с Telegram", bot.get_me)
        log.info("бот @%s запущен", me.username)
        await setup(bot, settings)
        if not settings.admin_ids:
            log.warning("ADMIN_IDS не задан: жалобы на заявки некому разбирать")

        started = datetime.now(timezone.utc)
        tasks += [
            asyncio.create_task(every(OUTBOX_EVERY, "отправлено событий",
                                      lambda: send_outbox_once(bot, pool, settings))),
            asyncio.create_task(every(POLL_EVERY, "отправлено по подпискам", lambda: notify_once(
                bot, pool, settings, max(started, datetime.now(timezone.utc) - LOOKBACK)))),
            asyncio.create_task(every(REMIND_EVERY, "напоминаний", lambda: remind_once(pool))),
        ]
        await make_dispatcher(settings, pool).start_polling(bot)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await bot.session.close()
        try:
            await asyncio.wait_for(pool.close(), 10)
        except Exception:
            pool.terminate()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("бот остановлен")


if __name__ == "__main__":
    main()
