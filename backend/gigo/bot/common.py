"""Общее для обработчиков бота: меню, клавиатуры, карточки заявок."""

import logging

from aiogram import BaseMiddleware, F
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from gigo import config, i18n
from gigo.i18n import N_, tr
from gigo.bot.look import edit
from gigo.bot.loops import keyboard
from gigo.categories import CATEGORIES
from gigo.format import esc, job_message

log = logging.getLogger("gigo.bot")

# Кнопки постоянного меню под полем ввода. Русские ключи: на кнопке — перевод на язык человека.
BTN_FIND = N_("🔎 Найти работу")
BTN_NEAR = N_("📍 Работа рядом")
BTN_NEW = N_("➕ Создать заявку")
BTN_MY = N_("📋 Мои заявки")
BTN_RESPONSES = N_("🙋 Мои отклики")
BTN_SUBS = N_("🔔 Подписки")
MENU_BUTTONS = (BTN_FIND, BTN_NEAR, BTN_NEW, BTN_MY, BTN_RESPONSES, BTN_SUBS)
# все переводы кнопок меню: старое меню на другом языке тоже работает
MENU_TEXTS = frozenset().union(*(i18n.variants(b) for b in MENU_BUTTONS))


def is_btn(key: str):
    """Фильтр: нажата кнопка меню key на любом из языков."""
    return F.text.in_(i18n.variants(key))


# Ответ на вопрос бота: обычный текст, не команда и не кнопка меню (те прерывают диалог).
ANSWER = F.text & ~F.text.startswith("/") & ~F.text.in_(MENU_TEXTS)


def menu() -> ReplyKeyboardMarkup:
    """Постоянное меню на языке текущего пользователя."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=tr(BTN_FIND)), KeyboardButton(text=tr(BTN_NEAR), request_location=True)],
            [KeyboardButton(text=tr(BTN_NEW)), KeyboardButton(text=tr(BTN_MY))],
            [KeyboardButton(text=tr(BTN_RESPONSES)), KeyboardButton(text=tr(BTN_SUBS))],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=tr("Выберите действие"),
    )


# Русские ключи: показывать через tr(STATUS[...]).
STATUS = {"pending": N_("⏳ ждёт ответа"), "accepted": N_("✅ принят"), "rejected": N_("✖️ отклонён"),
          "withdrawn": N_("↩️ отозван")}
JOB_STATUS = {"open": N_("🟢 идёт набор"), "closed": N_("🔒 набор закрыт"), "cancelled": N_("❌ отменена")}


class Kb:
    """Сборка inline-клавиатур: data нажимается в чате, path открывает Mini App (если задан WEBAPP_URL)."""

    def __init__(self, settings: config.Settings):
        self.settings = settings

    def __call__(self, *rows: list[dict] | None):
        return keyboard(self.settings, [r for r in rows if r])


def btn(text: str, data: str, style: str | None = None) -> dict:
    """style: success (зелёная), danger (красная), primary (синяя)."""
    return {"text": text, "data": data, **({"style": style} if style else {})}


def app(text: str, path: str = "") -> dict:
    return {"text": text, "path": path}


def category_rows(prefix: str) -> list[list[dict]]:
    items = [btn(f"{emoji} {tr(label)}", f"{prefix}{key}") for key, (label, emoji) in CATEGORIES.items()]
    return [items[i:i + 2] for i in range(0, len(items), 2)]


def rating_text(rating, count) -> str:
    return f"★ {rating} ({count})" if count else tr("пока без отзывов")


NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def num(n: int) -> str:
    return NUMBERS[n - 1] if 1 <= n <= len(NUMBERS) else f"{n}."


def job_card(job, distance_km: float | None = None) -> str:
    """Подробная карточка заявки для чата."""
    lines = [job_message(job, job["metro_name"])]
    if job["address"] and job["metro_name"]:
        lines.append(f"🏠 {esc(job['address'])}")
    if distance_km is not None:
        lines.append(tr("🚶 {km} км от вас", km=f"{distance_km:.1f}"))
    if job["description"]:
        lines.append(f"\n<blockquote expandable>{esc(job['description'])}</blockquote>")
    else:
        lines.append("")
    lines.append(tr("👥 Нужно: <b>{n}</b> · принято: {accepted}", n=job['workers_needed'],
                    accepted=job['accepted_count']))
    lines.append(f"👤 {esc(job['employer_name'] or tr('Заказчик'))} · "
                 f"{rating_text(job['employer_rating'], job['employer_reviews'])}")
    return "\n".join(lines)


def short_line(n: int, job, distance_km: float | None = None) -> str:
    """Заявка в списке: номер, название и одна строка условий."""
    label, emoji = CATEGORIES.get(job["category"], CATEGORIES["other"])
    head = f"{num(n)} {emoji} <b>{esc(job['title'])}</b>"
    rest = [line for line in job_message(job, job["metro_name"]).split("\n")[2:] if line.strip()]
    if distance_km is not None:
        rest.append(tr("🚶 {km} км", km=f"{distance_km:.1f}"))
    return head + ("\n" + " · ".join(rest) if rest else "")


async def note(call: CallbackQuery, text: str, markup=None) -> None:
    """Дописывает итог в сообщение с кнопками и меняет кнопки."""
    try:
        await edit(call.message, f"{call.message.html_text}\n\n<b>{text}</b>", markup)
    except Exception as e:  # сообщение могло быть старым или уже изменённым
        log.info("не удалось обновить сообщение: %s", e)


async def replace(call: CallbackQuery, text: str, markup=None) -> None:
    """Заменяет текст и кнопки сообщения, а если нельзя (старое сообщение), присылает новое."""
    try:
        await edit(call.message, text, markup)
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
                """INSERT INTO users (tg_id, username, first_name, lang) VALUES ($1, $2, $3, $4)
                   ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username,
                       first_name = EXCLUDED.first_name, lang = COALESCE(users.lang, EXCLUDED.lang),
                       bot_blocked = FALSE, last_seen_at = now()
                   RETURNING banned_at, role, lang""",
                user.id, user.username, (user.first_name or "")[:64] or None, i18n.normalize(user.language_code),
            )
            # дальше tr() в обработчиках отвечает на языке этого человека
            i18n.set_lang(row["lang"])
            data["lang"] = i18n.current()
            if row["banned_at"]:
                text = tr("Аккаунт заблокирован за нарушение правил Gigo.")
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
