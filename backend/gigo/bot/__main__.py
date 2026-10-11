"""Бот: открывает Mini App, присылает новые заявки по подпискам и события по откликам.

    python -m gigo.bot
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Message, WebAppInfo

from gigo import config, db
from gigo.format import job_message
from gigo.migrate import migrate

log = logging.getLogger("gigo.bot")

POLL_EVERY = 15        # секунд между проверками новых заявок
OUTBOX_EVERY = 3       # секунд между проверками очереди событий
MAX_ATTEMPTS = 5
LOOKBACK = timedelta(minutes=10)
SEND_PAUSE = 0.05      # Telegram разрешает ~30 сообщений в секунду

# Новые заявки × подписки, которым они подходят и о которых человеку ещё не писали.
MATCHES_SQL = """
SELECT DISTINCT ON (j.id, s.user_id)
       j.id, j.category, j.title, j.pay_per_hour, j.pay_estimated, j.pay_total, j.pay_amount, j.pay_unit,
       j.pay_timing, j.starts_on, j.starts_at, j.duration_hours, j.address,
       m.name AS metro_name, s.user_id, s.id AS subscription_id, s.name AS subscription_name
FROM jobs j
JOIN subscriptions s ON s.enabled
JOIN users u ON u.tg_id = s.user_id AND NOT u.bot_blocked
LEFT JOIN metro_stations m ON m.id = j.metro_id
LEFT JOIN notifications n ON n.user_id = s.user_id AND n.job_id = j.id
WHERE j.created_at > $1 AND j.status = 'open' AND j.expires_at > now() AND n.job_id IS NULL
  AND s.user_id <> j.employer_id
  AND (cardinality(s.categories) = 0 OR j.category = ANY(s.categories))
  AND (s.pay_min IS NULL OR j.pay_per_hour >= s.pay_min)
  AND (cardinality(s.metro_ids) = 0 OR j.metro_id = ANY(s.metro_ids))
  AND (s.location IS NULL OR ST_DWithin(j.location, s.location, coalesce(s.radius_km, 5) * 1000))
  AND (NOT s.today_only OR j.starts_on = (now() AT TIME ZONE 'Europe/Moscow')::date
       OR (j.starts_on IS NULL AND j.created_at > now() - interval '12 hours'))
ORDER BY j.id, s.user_id, s.id
"""


def app_button(settings: config.Settings, text: str, path: str = "") -> InlineKeyboardMarkup | None:
    if not settings.webapp_url:
        return None
    url = settings.webapp_url.rstrip("/") + "/" + path
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))]])


def make_dispatcher(settings: config.Settings, pool) -> Dispatcher:
    dp = Dispatcher()

    async def remember(message: Message) -> None:
        u = message.from_user
        await pool.execute(
            """INSERT INTO users (tg_id, username, first_name) VALUES ($1, $2, $3)
               ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username, first_name = EXCLUDED.first_name,
                   bot_blocked = FALSE, last_seen_at = now()""",
            u.id, u.username, u.first_name,
        )

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        await remember(message)
        await message.answer(
            "Gigo: подработка в Москве без посредников.\n\n"
            "Нужны люди на смену, переезд или разгрузку? Создайте заявку и выберите исполнителей из откликов.\n"
            "Ищете подработку? Смотрите заявки в ленте и на карте и откликайтесь в один тап.\n\n"
            "Здесь же будут приходить отклики, ответы заказчиков и новые заявки по вашим подпискам.",
            reply_markup=app_button(settings, "Открыть Gigo"),
        )

    @dp.message(Command("subs"))
    async def subs(message: Message) -> None:
        rows = await pool.fetch(
            "SELECT name, enabled FROM subscriptions WHERE user_id = $1 ORDER BY id", message.from_user.id
        )
        if not rows:
            text = "Подписок пока нет. Откройте ленту, настройте фильтр и нажмите «Подписаться»."
        else:
            text = "Ваши подписки:\n" + "\n".join(f"{'🔔' if r['enabled'] else '🔕'} {r['name']}" for r in rows)
        await message.answer(text, reply_markup=app_button(settings, "Управлять подписками"))

    @dp.message(Command("stop"))
    async def stop(message: Message) -> None:
        await pool.execute("UPDATE subscriptions SET enabled = FALSE WHERE user_id = $1", message.from_user.id)
        await message.answer("Уведомления о новых заявках выключены. Подписки можно включить заново в приложении.")

    @dp.message()
    async def other(message: Message) -> None:
        await message.answer("Заявки и отклики в приложении 👇", reply_markup=app_button(settings, "Открыть Gigo"))

    return dp


async def notify_once(bot: Bot, pool, settings: config.Settings, since: datetime) -> int:
    rows = await pool.fetch(MATCHES_SQL, since)
    sent = 0
    for r in rows:
        claimed = await pool.fetchval(
            "INSERT INTO notifications (user_id, job_id, subscription_id) VALUES ($1, $2, $3) "
            "ON CONFLICT DO NOTHING RETURNING 1",
            r["user_id"], r["id"], r["subscription_id"],
        )
        if not claimed:
            continue
        text = job_message(r, r["metro_name"], r["subscription_name"])
        try:
            await bot.send_message(r["user_id"], text, reply_markup=app_button(settings, "Подробнее", f"?job={r['id']}"))
            sent += 1
        except TelegramRetryAfter as e:
            await pool.execute("DELETE FROM notifications WHERE user_id = $1 AND job_id = $2", r["user_id"], r["id"])
            await asyncio.sleep(e.retry_after)
        except TelegramForbiddenError:
            await pool.execute("UPDATE users SET bot_blocked = TRUE WHERE tg_id = $1", r["user_id"])
        except TelegramBadRequest as e:
            log.warning("не отправилось %s: %s", r["user_id"], e)
        await asyncio.sleep(SEND_PAUSE)
    return sent


async def send_outbox_once(bot: Bot, pool, settings: config.Settings) -> int:
    """Отправляет накопившиеся события по откликам. Каждое уходит один раз."""
    rows = await pool.fetch(
        "SELECT o.id, o.user_id, o.text, o.button_text, o.button_path FROM outbox o "
        "JOIN users u ON u.tg_id = o.user_id "
        "WHERE o.sent_at IS NULL AND o.attempts < $1 AND NOT u.bot_blocked ORDER BY o.id LIMIT 100",
        MAX_ATTEMPTS,
    )
    sent = 0
    for r in rows:
        claimed = await pool.fetchval(
            "UPDATE outbox SET sent_at = now(), attempts = attempts + 1 WHERE id = $1 AND sent_at IS NULL RETURNING 1",
            r["id"],
        )
        if not claimed:
            continue
        markup = app_button(settings, r["button_text"], r["button_path"] or "") if r["button_text"] else None
        try:
            await bot.send_message(r["user_id"], r["text"], reply_markup=markup)
            sent += 1
        except TelegramRetryAfter as e:
            await pool.execute("UPDATE outbox SET sent_at = NULL WHERE id = $1", r["id"])
            await asyncio.sleep(e.retry_after)
        except TelegramForbiddenError:
            await pool.execute("UPDATE users SET bot_blocked = TRUE WHERE tg_id = $1", r["user_id"])
        except TelegramBadRequest as e:
            log.warning("событие %s не отправилось: %s", r["id"], e)
        except Exception:
            await pool.execute("UPDATE outbox SET sent_at = NULL WHERE id = $1", r["id"])
            raise
        await asyncio.sleep(SEND_PAUSE)
    return sent


async def outbox_sender(bot: Bot, pool, settings: config.Settings) -> None:
    while True:
        try:
            if sent := await send_outbox_once(bot, pool, settings):
                log.info("отправлено событий: %d", sent)
        except Exception:
            log.exception("ошибка отправки событий")
        await asyncio.sleep(OUTBOX_EVERY)


async def notifier(bot: Bot, pool, settings: config.Settings) -> None:
    started = datetime.now(timezone.utc)
    while True:
        try:
            since = max(started, datetime.now(timezone.utc) - LOOKBACK)
            if sent := await notify_once(bot, pool, settings, since):
                log.info("отправлено уведомлений: %d", sent)
        except Exception:
            log.exception("ошибка рассылки")
        await asyncio.sleep(POLL_EVERY)


async def run() -> None:
    settings = config.load()
    if not settings.bot_token:
        raise SystemExit("Не задан BOT_TOKEN: получите его у @BotFather и впишите в .env")
    await migrate(settings.database_url)
    pool = await db.connect(settings.database_url)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    if settings.webapp_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Gigo", web_app=WebAppInfo(url=settings.webapp_url))
        )
    else:
        log.warning("WEBAPP_URL не задан: кнопки открытия приложения не будет")
    dp = make_dispatcher(settings, pool)
    tasks = [asyncio.create_task(notifier(bot, pool, settings)),
             asyncio.create_task(outbox_sender(bot, pool, settings))]
    try:
        await dp.start_polling(bot)
    finally:
        for task in tasks:
            task.cancel()
        await pool.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
