"""Диалоги с ботом целиком: апдейты идут через диспетчер, запросы к Telegram перехватывает FakeSession."""

import itertools
from datetime import datetime, timedelta, timezone

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.methods import (AnswerCallbackQuery, EditMessageCaption, EditMessageReplyMarkup, EditMessageText,
                             SendMessage, SendPhoto)
from aiogram.types import CallbackQuery, Chat, Location, Message, PhotoSize, Update, User

from gigo import config
from gigo.bot.handlers import make_dispatcher
from gigo.bot.loops import notify_once, remind_once, send_outbox_once
from gigo.rules import MSK
from tests.test_api import _metro

EMPLOYER, WORKER = 555, 777
_ids = itertools.count(1)


class FakeSession(BaseSession):
    """Вместо Telegram: запоминает отправленные сообщения и ответы на нажатия."""

    def __init__(self):
        super().__init__()
        self.messages: dict[int, dict] = {}   # message_id → {"chat", "text", "markup"}
        self.alerts: list[tuple[int, str | None, bool]] = []

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            mid = next(_ids)
            self.messages[mid] = {"chat": method.chat_id, "text": method.text, "markup": method.reply_markup}
            return _message(mid, method.chat_id, method.text, method.reply_markup, bot_id=bot.id)
        if isinstance(method, SendPhoto):
            mid = next(_ids)
            self.messages[mid] = {"chat": method.chat_id, "text": method.caption, "markup": method.reply_markup,
                                  "photo": method.photo}
            return _message(mid, method.chat_id, None, method.reply_markup, bot_id=bot.id, caption=method.caption,
                            photo=[PhotoSize(file_id=f"photo{mid}", file_unique_id=f"u{mid}", width=1280, height=640)])
        if isinstance(method, EditMessageText):
            assert not self.messages[method.message_id].get("photo"), "у сообщения с баннером меняют подпись"
            self.messages[method.message_id].update(text=method.text, markup=method.reply_markup)
            return True
        if isinstance(method, EditMessageCaption):
            self.messages[method.message_id].update(text=method.caption, markup=method.reply_markup)
            return True
        if isinstance(method, EditMessageReplyMarkup):
            self.messages[method.message_id]["markup"] = method.reply_markup
            return True
        if isinstance(method, AnswerCallbackQuery):
            self.alerts.append((method.callback_query_id, method.text, bool(method.show_alert)))
            return True
        return True

    async def close(self):
        pass

    async def stream_content(self, *a, **kw):  # pragma: no cover
        yield b""


def _message(mid, chat_id, text, markup=None, bot_id=None, from_id=None, **kw) -> Message:
    sender = User(id=bot_id, is_bot=True, first_name="Gigo") if bot_id else \
        User(id=from_id, is_bot=False, first_name=f"user{from_id}")
    return Message(message_id=mid, date=datetime.now(timezone.utc), chat=Chat(id=chat_id, type="private"),
                   from_user=sender, text=text, reply_markup=markup if hasattr(markup, "inline_keyboard") else None,
                   **kw)


class Chat_:
    """Пользователь, который пишет боту и жмёт кнопки."""

    def __init__(self, env, user_id: int, name: str):
        self.env, self.id, self.name = env, user_id, name

    @property
    def user(self) -> User:
        return User(id=self.id, is_bot=False, first_name=self.name, username=self.name.lower())

    async def say(self, text: str = None, **kw) -> None:
        msg = Message(message_id=next(_ids), date=datetime.now(timezone.utc), chat=Chat(id=self.id, type="private"),
                      from_user=self.user, text=text, **kw)
        await self.env.dp.feed_update(self.env.bot, Update(update_id=next(_ids), message=msg))

    async def location(self, lat: float, lng: float) -> None:
        await self.say(location=Location(latitude=lat, longitude=lng))

    def inbox(self) -> list[dict]:
        return [m | {"id": mid} for mid, m in self.env.session.messages.items() if m["chat"] == self.id]

    def last(self) -> str:
        return self.inbox()[-1]["text"]

    async def press(self, label: str) -> None:
        """Нажимает кнопку с такой подписью в самом свежем сообщении, где она есть."""
        for m in reversed(self.inbox()):
            markup = m["markup"]
            for row in getattr(markup, "inline_keyboard", []) or []:
                for b in row:
                    if b.text == label and b.callback_data:
                        if m.get("photo"):
                            msg = _message(m["id"], self.id, None, markup, bot_id=self.env.bot.id, caption=m["text"],
                                           photo=[PhotoSize(file_id="p", file_unique_id="u", width=1, height=1)])
                        else:
                            msg = _message(m["id"], self.id, m["text"], markup, bot_id=self.env.bot.id)
                        call = CallbackQuery(id=str(next(_ids)), from_user=self.user, chat_instance="ci",
                                             message=msg, data=b.callback_data)
                        await self.env.dp.feed_update(self.env.bot, Update(update_id=next(_ids), callback_query=call))
                        return
        raise AssertionError(f"нет кнопки {label!r}; последние сообщения: {[m['text'][:60] for m in self.inbox()[-3:]]}")

    def alerts(self) -> list[str]:
        return [text for _, text, _ in self.env.session.alerts if text]


class Env:
    def __init__(self, pool, settings):
        self.session = FakeSession()
        self.bot = Bot("123456:TEST", session=self.session, default=DefaultBotProperties(parse_mode="HTML"))
        self.dp = make_dispatcher(settings, pool)
        self.pool, self.settings = pool, settings

    async def deliver(self) -> None:
        await send_outbox_once(self.bot, self.pool, self.settings)


@pytest.fixture
async def env(pool, monkeypatch):
    monkeypatch.delenv("WEBAPP_URL", raising=False)   # как сейчас, без VPS: всё должно работать без Mini App
    monkeypatch.delenv("YANDEX_GEOCODER_KEY", raising=False)
    monkeypatch.setenv("ADMIN_IDS", "")
    await _metro(pool)
    return Env(pool, config.load())


async def _create_job(emp: Chat_, title="Разгрузить фуру с мебелью", day="Завтра", workers="2") -> int:
    await emp.say("/new")
    await emp.press("📦 Грузчики")
    await emp.say(title)
    await emp.press("За смену")
    await emp.say("3 000 ₽")
    await emp.press(day)
    if day != "Без даты, когда удобно":
        await emp.press("09:00")
    await emp.press("8 ч")
    await emp.say("таганская, Марксистская 3")
    await emp.say(workers)
    await emp.press("Пропустить")
    assert "Проверьте заявку" in emp.last()
    await emp.press("✅ Опубликовать")
    assert "опубликована" in emp.last()
    return await emp.env.pool.fetchval("SELECT max(id) FROM jobs WHERE employer_id = $1", emp.id)


async def test_start_asks_role(env):
    me = Chat_(env, WORKER, "Иван")
    await me.say("/start")
    assert "Что вы ищете?" in me.last()
    await me.press("🔎 Ищу подработку")
    assert await env.pool.fetchval("SELECT role FROM users WHERE tg_id = $1", WORKER) == "worker"


async def test_create_job_dialog(env):
    emp = Chat_(env, EMPLOYER, "Ольга")
    job_id = await _create_job(emp)
    job = await env.pool.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
    tomorrow = datetime.now(MSK).date() + timedelta(days=1)
    assert job["category"] == "loader" and job["title"] == "Разгрузить фуру с мебелью"
    assert job["metro_id"] == "7.1" and job["address"] == "Марксистская 3"
    assert float(job["pay_per_hour"]) == 375 and job["workers_needed"] == 2
    assert job["starts_at"].astimezone(MSK).replace(tzinfo=None) == datetime(tomorrow.year, tomorrow.month,
                                                                              tomorrow.day, 9)
    # роль ставится по первому действию
    assert await env.pool.fetchval("SELECT role FROM users WHERE tg_id = $1", EMPLOYER) == "employer"


async def test_dialog_validation_and_interrupt(env):
    emp = Chat_(env, EMPLOYER, "Ольга")
    await emp.say("/new")
    await emp.press("📦 Грузчики")
    await emp.say("ок")
    assert "от 3 до 100" in emp.last()
    await emp.say("Закладки по району, высокий доход")
    assert "нельзя" in emp.last()
    await emp.say("Разгрузить машину")
    await emp.press("За час")
    await emp.say("много")
    assert "числом" in emp.last()
    # команда посреди диалога не попадает в ответ, а прерывает его
    await emp.say("/jobs")
    assert "Свежие заявки" in emp.last()
    await emp.say("500")
    assert "Не понял" in emp.last()
    assert await env.pool.fetchval("SELECT count(*) FROM jobs") == 0


async def test_metro_choice_and_location(env):
    emp = Chat_(env, EMPLOYER, "Ольга")
    await emp.say("/new")
    await emp.press("🧹 Уборка")
    await emp.say("Помыть окна в офисе")
    await emp.press("За работу")
    await emp.say("5000")
    await emp.press("Без даты, когда удобно")
    await emp.press("Не знаю")
    await emp.say("Реч")                          # неполное название: бот предлагает станции
    await emp.press("Ⓜ️ Речной вокзал (Замоскворецкая)")
    await emp.press("1")
    await emp.say("Окна на 3 этаже, стремянка есть")
    await emp.press("✅ Опубликовать")
    job = await env.pool.fetchrow("SELECT * FROM jobs ORDER BY id DESC LIMIT 1")
    assert job["metro_id"] == "2.1" and job["description"] == "Окна на 3 этаже, стремянка есть"
    assert job["starts_on"] is None and job["location"] is not None

    await emp.say("/new")
    await emp.press("🧹 Уборка")
    await emp.say("Убрать квартиру")
    await emp.press("За работу")
    await emp.say("4000")
    await emp.press("Без даты, когда удобно")
    await emp.press("Не знаю")
    await emp.location(55.7400, 37.6540)          # рядом с Таганской
    assert "Таганская" in emp.inbox()[-2]["text"]
    await emp.press("1")
    await emp.press("Пропустить")
    await emp.press("✅ Опубликовать")
    job = await env.pool.fetchrow("SELECT * FROM jobs ORDER BY id DESC LIMIT 1")
    assert job["metro_id"] == "7.1" and job["address"] is None


async def test_find_respond_accept_review(env):
    emp, me = Chat_(env, EMPLOYER, "Ольга"), Chat_(env, WORKER, "Иван")
    job_id = await _create_job(emp)

    await me.say("🔎 Найти работу")
    assert "Разгрузить фуру" in me.last()
    await me.press("1")
    assert "Разгрузить фуру" in me.last() and "Ольга" in me.last()
    await me.press("🙋 Откликнуться")
    assert "Отклик отправлен" in me.last()
    assert await env.pool.fetchval("SELECT status FROM responses WHERE job_id = $1", job_id) == "pending"

    # заказчику приходит отклик с кнопками, принимает прямо в чате
    await env.deliver()
    assert "Новый отклик" in emp.last()
    await emp.press("✅ Принять")
    assert await env.pool.fetchval("SELECT status FROM responses WHERE job_id = $1", job_id) == "accepted"
    await env.deliver()
    assert "Вас выбрали" in me.last() and "@ольга" in me.last()

    # работа закончилась: обеим сторонам приходят звёзды
    await env.pool.execute("UPDATE jobs SET starts_at = now() - interval '9 hours' WHERE id = $1", job_id)
    assert await remind_once(env.pool) == 2
    await env.deliver()
    await me.press("5★")
    await me.say("Всё чётко, заплатили сразу")
    review = await env.pool.fetchrow("SELECT * FROM reviews WHERE author_id = $1", WORKER)
    assert review["rating"] == 5 and review["text"] == "Всё чётко, заплатили сразу" and review["target_id"] == EMPLOYER
    await emp.press("4★")
    await emp.press("Готово")
    review = await env.pool.fetchrow("SELECT * FROM reviews WHERE author_id = $1", EMPLOYER)
    assert review["rating"] == 4 and review["target_id"] == WORKER


async def test_respond_with_message_and_withdraw(env):
    emp, me = Chat_(env, EMPLOYER, "Ольга"), Chat_(env, WORKER, "Иван")
    job_id = await _create_job(emp)
    await me.say(f"/start job_{job_id}")
    await me.press("☆ В избранное")
    assert await env.pool.fetchval("SELECT count(*) FROM saved_jobs WHERE user_id = $1", WORKER) == 1
    await me.press("✍️ С сообщением")
    await me.say("Есть опыт, приеду к 9")
    assert await env.pool.fetchval("SELECT message FROM responses WHERE job_id = $1", job_id) == "Есть опыт, приеду к 9"
    await me.say("/responses")
    assert "ждёт ответа" in me.last()
    await me.press("↩️ Отозвать отклик")
    assert await env.pool.fetchval("SELECT status FROM responses WHERE job_id = $1", job_id) == "withdrawn"


async def test_near_and_subscriptions(env):
    emp, me = Chat_(env, EMPLOYER, "Ольга"), Chat_(env, WORKER, "Иван")
    await _create_job(emp)
    await me.location(55.7393, 37.6533)
    assert "Работа в 10 км" in me.last() and "Разгрузить" in me.last()
    await me.location(55.95, 37.2)               # далеко: пусто
    assert "Пока ничего нет" in me.last()

    await me.say("🔔 Подписки")
    await me.press("➕ По категории")
    await me.press("📦 Грузчики")
    assert await env.pool.fetchval("SELECT categories FROM subscriptions WHERE user_id = $1", WORKER) == ["loader"]
    await me.press("🔔 📦 Грузчики")              # выключить
    assert await env.pool.fetchval("SELECT enabled FROM subscriptions WHERE user_id = $1", WORKER) is False
    await me.press("🔕 📦 Грузчики")
    # новая заявка приходит по подписке с кнопкой отклика прямо в чате
    job_id = await _create_job(emp, title="Перенести мебель на склад")
    since = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert await notify_once(env.bot, env.pool, env.settings, since) == 2  # обе заявки «Грузчики»
    assert "Перенести мебель" in me.last()
    await me.press("🙋 Откликнуться")
    assert await env.pool.fetchval("SELECT count(*) FROM responses WHERE job_id = $1", job_id) == 1


async def test_manage_close_repeat(env):
    emp, me = Chat_(env, EMPLOYER, "Ольга"), Chat_(env, WORKER, "Иван")
    job_id = await _create_job(emp)
    await me.say(f"/start job_{job_id}")
    await me.press("🙋 Откликнуться")

    await emp.say("📋 Мои заявки")
    assert "новых откликов: 1" in emp.last()
    await emp.press("1")
    await emp.press("👥 Отклики (1)")
    assert "Иван" in emp.last()
    await emp.press("🔒 Закрыть набор")
    assert await env.pool.fetchval("SELECT status FROM jobs WHERE id = $1", job_id) == "closed"
    assert await env.pool.fetchval("SELECT status FROM responses WHERE job_id = $1", job_id) == "rejected"
    await emp.press("🔁 Повторить на другой день")
    await emp.press("Послезавтра")
    new = await env.pool.fetchrow("SELECT * FROM jobs WHERE id <> $1", job_id)
    assert new["title"] == "Разгрузить фуру с мебелью" and new["status"] == "open" and new["workers_needed"] == 2
    assert new["starts_on"] == datetime.now(MSK).date() + timedelta(days=2)
    assert new["starts_at"].astimezone(MSK).hour == 9

    await emp.press("❌ Отменить")
    await emp.press("Да, отменить заявку")
    assert await env.pool.fetchval("SELECT status FROM jobs WHERE id = $1", new["id"]) == "cancelled"
    # чужой заявкой управлять нельзя
    await me.say("/start")
    await me.env.dp.feed_update(env.bot, Update(update_id=next(_ids), callback_query=CallbackQuery(
        id="x", from_user=me.user, chat_instance="ci", data=f"jc:{job_id}",
        message=_message(next(_ids), WORKER, "x", bot_id=env.bot.id))))
    assert me.alerts()[-1] == "Заявка не найдена"


async def test_banned_and_stale_buttons(env):
    me = Chat_(env, WORKER, "Иван")
    await me.say("/start")
    await me.env.dp.feed_update(env.bot, Update(update_id=next(_ids), callback_query=CallbackQuery(
        id="y", from_user=me.user, chat_instance="ci", data="nj:cat:loader",
        message=_message(next(_ids), WORKER, "x", bot_id=env.bot.id))))
    assert "устарела" in me.alerts()[-1]
    await env.pool.execute("UPDATE users SET banned_at = now() WHERE tg_id = $1", WORKER)
    await me.say("/jobs")
    assert "заблокирован" in me.last()


async def test_banners_and_custom_emoji(env, monkeypatch):
    from gigo.bot import look

    me = Chat_(env, WORKER, "Иван")
    await me.say("/start")
    welcome = me.inbox()[-1]
    assert welcome.get("photo") is not None and "Что вы ищете?" in welcome["text"]
    assert look.BANNERS.file_ids["welcome"].startswith("photo")   # второй раз уйдёт file_id, без загрузки
    await me.press("🔎 Ищу подработку")                          # подпись у баннера меняется, а не текст
    assert "Ищу подработку" in me.inbox()[-1]["text"]

    # нет картинки: обычное сообщение
    monkeypatch.setattr(look.BANNERS, "dir", look.BANNERS.dir / "нет")
    look.BANNERS.file_ids.clear()
    await me.say("/help")
    assert me.inbox()[-1].get("photo") is None and "Ищете подработку" in me.last()

    # премиум-эмодзи: подмена в тексте и на кнопках, при отказе Telegram откат на обычные
    look.EMOJI.set({"🔎": "111", "✅": "222"})
    env.bot.session.middleware(look.PrettyMiddleware())
    try:
        await me.say("/jobs")
        m = me.inbox()[-1]
        assert '<tg-emoji emoji-id="111">🔎</tg-emoji>' in m["text"]
        assert look.EMOJI.html('<a href="x">✅</a> ✅') == \
            '<a href="x"><tg-emoji emoji-id="222">✅</tg-emoji></a> <tg-emoji emoji-id="222">✅</tg-emoji>'
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        b = look.EMOJI.markup(InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Принять",
                                                                                          callback_data="x")]]))
        assert b.inline_keyboard[0][0].text == "Принять" and b.inline_keyboard[0][0].icon_custom_emoji_id == "222"

        from aiogram.exceptions import TelegramBadRequest
        real = env.session.make_request

        async def picky(bot, method, timeout=None):
            if "tg-emoji" in (getattr(method, "text", None) or ""):
                raise TelegramBadRequest(method=method, message="Bad Request: custom emoji entities are not allowed")
            return await real(bot, method, timeout)
        monkeypatch.setattr(env.session, "make_request", picky)
        await me.say("/jobs")
        assert "tg-emoji" not in me.last() and look.EMOJI.enabled is False
    finally:
        look.EMOJI.set({})
