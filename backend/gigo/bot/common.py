"""Общее для обработчиков бота: меню, клавиатуры, карточки заявок."""

import logging

from aiogram import BaseMiddleware, F
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from gigo import config
from gigo.bot.loops import keyboard
from gigo.categories import CATEGORIES
from gigo.format import esc, job_message

log = logging.getLogger("gigo.bot")

# Кнопки постоянного меню под полем ввода.
BTN_FIND = "🔎 Найти работу"
BTN_NEAR = "📍 Работа рядом"
BTN_NEW = "➕ Создать заявку"
BTN_MY = "📋 Мои заявки"
BTN_RESPONSES = "🙋 Мои отклики"
BTN_SUBS = "🔔 Подписки"
MENU_BUTTONS = (BTN_FIND, BTN_NEAR, BTN_NEW, BTN_MY, BTN_RESPONSES, BTN_SUBS)

# Ответ на вопрос бота: обычный текст, не команда и не кнопка меню (те прерывают диалог).
ANSWER = F.text & ~F.text.startswith("/") & ~F.text.in_(MENU_BUTTONS)

MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_FIND), KeyboardButton(text=BTN_NEAR, request_location=True)],
        [KeyboardButton(text=BTN_NEW), KeyboardButton(text=BTN_MY)],
        [KeyboardButton(text=BTN_RESPONSES), KeyboardButton(text=BTN_SUBS)],
    ],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Выберите действие",
)

STATUS = {"pending": "⏳ ждёт ответа", "accepted": "✅ принят", "rejected": "✖️ отклонён", "withdrawn": "↩️ отозван"}
JOB_STATUS = {"open": "🟢 идёт набор", "closed": "🔒 набор закрыт", "cancelled": "❌ отменена"}


class Kb:
    """Сборка inline-клавиатур: data нажимается в чате, path открывает Mini App (если задан WEBAPP_URL)."""

    def __init__(self, settings: config.Settings):
        self.settings = settings

    def __call__(self, *rows: list[dict] | None):
        return keyboard(self.settings, [r for r in rows if r])


def btn(text: str, data: str) -> dict:
    return {"text": text, "data": data}


def app(text: str, path: str = "") -> dict:
    return {"text": text, "path": path}


def category_rows(prefix: str) -> list[list[dict]]:
    items = [btn(f"{emoji} {label}", f"{prefix}{key}") for key, (label, emoji) in CATEGORIES.items()]
    return [items[i:i + 2] for i in range(0, len(items), 2)]


def rating_text(rating, count) -> str:
    return f"★ {rating} ({count})" if count else "пока без отзывов"


def job_card(job, distance_km: float | None = None) -> str:
    """Подробная карточка заявки для чата."""
    lines = [job_message(job, job["metro_name"])]
    if job["address"] and job["metro_name"]:
        lines.append(f"🏠 {esc(job['address'])}")
    if distance_km is not None:
        lines.append(f"🚶 {distance_km:.1f} км от вас")
    if job["description"]:
        lines.append(f"\n{esc(job['description'])}")
    need = job["workers_needed"]
    lines.append(f"\n👥 Нужно: {need} · принято: {job['accepted_count']}")
    lines.append(f"👤 Заказчик: {esc(job['employer_name'] or 'без имени')} · "
                 f"{rating_text(job['employer_rating'], job['employer_reviews'])}")
    return "\n".join(lines)


def short_line(n: int, job, distance_km: float | None = None) -> str:
    """Строка заявки в списке."""
    label, emoji = CATEGORIES.get(job["category"], CATEGORIES["other"])
    head = f"{n}. {emoji} <b>{esc(job['title'])}</b>"
    rest = job_message(job, job["metro_name"]).split("\n")[1:]
    if distance_km is not None:
        rest.append(f"🚶 {distance_km:.1f} км")
    return head + ("\n" + " · ".join(rest) if rest else "")


async def note(call: CallbackQuery, text: str, markup=None) -> None:
    """Дописывает итог в сообщение с кнопками и меняет кнопки."""
    try:
        await call.message.edit_text(f"{call.message.html_text}\n\n<b>{text}</b>", reply_markup=markup)
    except Exception as e:  # сообщение могло быть старым или уже изменённым
        log.info("не удалось обновить сообщение: %s", e)


async def replace(call: CallbackQuery, text: str, markup=None) -> None:
    """Заменяет текст и кнопки сообщения, а если нельзя (старое сообщение), присылает новое."""
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception as e:
        if "not modified" not in str(e):
            await call.message.answer(text, reply_markup=markup)


class UserMiddleware(BaseMiddleware):
    """Запоминает каждого, кто пишет боту, и не пускает заблокированных."""

    def __init__(self, pool):
        self.pool = pool

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and not user.is_bot:
            row = await self.pool.fetchrow(
                """INSERT INTO users (tg_id, username, first_name) VALUES ($1, $2, $3)
                   ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username,
                       first_name = EXCLUDED.first_name, bot_blocked = FALSE, last_seen_at = now()
                   RETURNING banned_at, role""",
                user.id, user.username, (user.first_name or "")[:64] or None,
            )
            if row["banned_at"]:
                text = "Аккаунт заблокирован за нарушение правил Gigo."
                if isinstance(event, CallbackQuery):
                    await event.answer(text, show_alert=True)
                elif isinstance(event, Message):
                    await event.answer(text)
                return None
            data["role"] = row["role"]
        return await handler(event, data)


async def ensure_role(pool, user_id: int, role: str) -> None:
    """Если роль ещё не выбрана, ставит её по первому действию. Выбранную не трогает: в боте доступно всё."""
    await pool.execute("UPDATE users SET role = $2 WHERE tg_id = $1 AND role IS NULL", user_id, role)
