"""Устойчивость бота: перехват любых ошибок в обработчиках, защита от флуда и мусорных кнопок, только личные чаты.

Правило: пользователь никогда не остаётся без ответа (крутящаяся кнопка, тишина), а бот не падает.
"""

import asyncio
import logging
import re
import time

import asyncpg
from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.exceptions import (TelegramBadRequest, TelegramEntityTooLarge, TelegramForbiddenError,
                                TelegramNetworkError, TelegramRetryAfter, TelegramServerError)
from aiogram.types import CallbackQuery, ChatMemberUpdated, ErrorEvent, Message

from gigo import i18n
from gigo.i18n import N_, tr

log = logging.getLogger("gigo.bot")

# Русские ключи: показывать через tr().
TEXT_DOWN = N_("⚠️ Сервис временно недоступен. Попробуйте через минуту.")
TEXT_FAIL = N_("⚠️ Что-то пошло не так. Попробуйте ещё раз, а если не выйдет, начните заново: /start")
TEXT_FLOOD = N_("Слишком часто. Подождите пару секунд.")

# Ответы Telegram, которые не ошибка: кнопку нажали дважды, сообщение старое или уже изменено.
HARMLESS = ("message is not modified", "query is too old", "query id is invalid", "message to edit not found",
            "message can't be edited", "message to delete not found", "message can't be deleted")

# Числа длиннее bigint в данных кнопки: подделка или мусор, в базу их не пускаем.
_HUGE_NUMBER = re.compile(r"\d{19,}")


def is_transient(e: BaseException) -> bool:
    """Сбой связи или временная недоступность Telegram: стоит повторить позже."""
    if isinstance(e, TelegramEntityTooLarge):
        return False
    return isinstance(e, (TelegramNetworkError, TelegramServerError, TelegramRetryAfter, asyncio.TimeoutError,
                          ConnectionError))


def is_db_down(e: BaseException) -> bool:
    """База недоступна или перегружена (а не ошибка в запросе)."""
    return isinstance(e, (OSError, asyncio.TimeoutError, asyncpg.InterfaceError,
                          asyncpg.CannotConnectNowError, asyncpg.TooManyConnectionsError,
                          asyncpg.ConnectionDoesNotExistError, asyncpg.AdminShutdownError))


def harmless(e: BaseException) -> bool:
    return isinstance(e, TelegramBadRequest) and any(s in str(e).lower() for s in HARMLESS)


class Guard(BaseMiddleware):
    """Первый фильтр входящих: только личные чаты, без флуда, без подделанных кнопок. До базы ничего не доходит.

    Флуд: у каждого пользователя «ведро» на BURST действий, пополняется на RATE в секунду.
    """

    BURST = 30
    RATE = 2.0

    def __init__(self):
        self.buckets: dict[int, list[float]] = {}   # user_id → [токены, время, предупреждён ли]

    def allow(self, user_id: int) -> tuple[bool, bool]:
        """(пропустить, предупредить). Предупреждаем один раз за приступ флуда."""
        now = time.monotonic()
        if len(self.buckets) > 50_000:  # чистим тех, кто давно не писал
            self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < 60}
        tokens, last, warned = self.buckets.get(user_id, (self.BURST, now, 0))
        tokens = min(self.BURST, tokens + (now - last) * self.RATE)
        if tokens >= 1:
            self.buckets[user_id] = [tokens - 1, now, 0]
            return True, False
        self.buckets[user_id] = [tokens, now, 1]
        return False, not warned

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user:  # пока не знаем язык из базы — язык Telegram; UserMiddleware потом уточнит
            i18n.set_lang(user.language_code)
        if isinstance(event, Message):
            if event.chat.type != "private":
                return None
        elif isinstance(event, CallbackQuery):
            if event.message and event.message.chat.type != "private":
                return None
            if event.data and _HUGE_NUMBER.search(event.data):
                await event.answer(tr("Эта кнопка устарела. Начните заново из меню."), show_alert=True)
                return None
        if user:
            ok, warn = self.allow(user.id)
            if not ok:
                log.warning("флуд от %s, событие пропущено", user.id)
                if isinstance(event, CallbackQuery):
                    await event.answer(tr(TEXT_FLOOD))
                elif warn and isinstance(event, Message):
                    await event.answer(tr(TEXT_FLOOD))
                return None
        return await handler(event, data)


def install(dp: Dispatcher, pool) -> None:
    """Подключает защиту к диспетчеру. Вызывать до остальных middleware."""
    guard = Guard()
    dp.message.outer_middleware(guard)
    dp.callback_query.outer_middleware(guard)

    @dp.my_chat_member()
    async def membership(update: ChatMemberUpdated, bot: Bot) -> None:
        """Бота добавили в группу: выходим. В личке запоминаем, заблокировал ли человек бота."""
        status = update.new_chat_member.status
        if update.chat.type != "private":
            if status in ("member", "administrator"):
                log.info("бота добавили в чат %s, выхожу", update.chat.id)
                try:
                    await bot.leave_chat(update.chat.id)
                except Exception as e:
                    log.info("не вышел из чата %s: %s", update.chat.id, e)
            return
        await pool.execute("UPDATE users SET bot_blocked = $2 WHERE tg_id = $1",
                           update.from_user.id, status == "kicked")

    @dp.errors()
    async def on_error(event: ErrorEvent, bot: Bot) -> bool:
        """Любая ошибка в обработчике: пишем в лог и коротко отвечаем человеку, чтобы он не ждал впустую."""
        e, update = event.exception, event.update
        call, message = update.callback_query, update.message
        user = (call or message).from_user if (call or message) else None

        if harmless(e):
            log.info("telegram: %s", e)
            if call:
                await _quiet(call.answer())
            return True
        if isinstance(e, TelegramForbiddenError):
            if user:
                await _quiet(pool.execute("UPDATE users SET bot_blocked = TRUE WHERE tg_id = $1", user.id))
            return True
        if is_transient(e):
            # До Telegram не достучаться: ответить всё равно не выйдет.
            log.warning("telegram недоступен при обработке %s: %r", update.event_type, e)
            return True

        down = is_db_down(e)
        if down:
            log.error("база недоступна при обработке %s: %r", update.event_type, e)
        else:
            log.error("ошибка при обработке %s от %s", update.event_type, user.id if user else "?", exc_info=e)
            if user:
                # Состояние диалога могло испортиться: сбрасываем, чтобы человек не застрял.
                chat_id = message.chat.id if message else (call.message.chat.id if call.message else user.id)
                await _quiet(dp.fsm.get_context(bot, chat_id=chat_id, user_id=user.id).clear())
        text = tr(TEXT_DOWN if down else TEXT_FAIL)
        # На нажатие отвечаем всплывающим окном; если на него уже ответили, пишем сообщением.
        if not (call and await _quiet(call.answer(text, show_alert=True))) and user:
            await _quiet(bot.send_message(user.id, text))
        return True


async def _quiet(coro) -> bool:
    """Попытка ответить из обработчика ошибок: если и она не вышла, только пишем в лог."""
    try:
        await coro
        return True
    except Exception as e:
        log.info("не удалось ответить после ошибки: %r", e)
        return False
