"""Исполнитель в боте: лента, работа рядом, карточка заявки, отклик, мои отклики, подписки."""

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from gigo import actions, config, events
from gigo.bot.common import (ANSWER, BTN_FIND, BTN_NEAR, BTN_RESPONSES, BTN_SUBS, MENU, STATUS, Kb, app, btn,
                             category_rows, ensure_role, job_card, note, replace, short_line)
from gigo.categories import CATEGORIES
from gigo.format import esc
from gigo.jobs_query import JobFilter, build_feed, jobs_where

PAGE = 5
NEAR_KM = 10
SUB_NEAR_KM = 3
MAX_SUBSCRIPTIONS = 10
MAX_SAVED = 200


class RespondForm(StatesGroup):
    message = State()


class SubForm(StatesGroup):
    location = State()


def make_router(settings: config.Settings, pool):
    """Возвращает (router, send_card): send_card нужен для ссылок вида /start job_42."""
    r = Router(name="browse")
    kb = Kb(settings)

    # --- лента ------------------------------------------------------------------

    async def feed_page(user_id: int, cat: str, offset: int, lat: float | None = None, lng: float | None = None):
        near = lat is not None
        f = JobFilter(categories=[cat] if cat != "*" else [], lat=lat, lng=lng,
                      radius_km=NEAR_KM if near else None, sort="distance" if near else "fresh",
                      limit=PAGE, offset=offset)
        list_sql, count_sql, params = build_feed(f, user_id)
        rows = await pool.fetch(list_sql, *params)
        total = await pool.fetchval(count_sql, *params)
        if near:
            title = f"<b>Работа в {NEAR_KM} км от вас</b>"
            base = f"near:{lat:.4f}:{lng:.4f}:"
        else:
            title = "<b>Свежие заявки</b>" + (f" · {CATEGORIES[cat][0]}" if cat != "*" else "")
            base = f"feed:{cat}:"
        if not rows:
            text = title + "\n\nПока ничего нет. Подпишитесь, и новые заявки будут приходить сюда сами."
            return text, kb([btn("🔔 Подписаться", "sub:new")],
                            [btn("🗂 Другая категория", "fcat")] if not near else None)
        lines = [title + f" · {offset + 1}–{offset + len(rows)} из {total}"]
        for i, job in enumerate(rows, start=1):
            lines.append(short_line(i, job, job["distance_km"]))
        numbers = [btn(str(i), f"job:{job['id']}") for i, job in enumerate(rows, start=1)]
        nav = []
        if offset > 0:
            nav.append(btn("◀️", f"{base}{max(offset - PAGE, 0)}"))
        if not near:
            nav.append(btn("🗂 Категория", "fcat"))
        if offset + PAGE < total:
            nav.append(btn("▶️", f"{base}{offset + PAGE}"))
        text = "\n\n".join(lines) + "\n\nНажмите номер, чтобы открыть заявку и откликнуться."
        return text, kb(numbers, nav)

    @r.message(Command("jobs"))
    @r.message(F.text == BTN_FIND)
    async def find(message: Message, state: FSMContext) -> None:
        await state.clear()
        text, markup = await feed_page(message.from_user.id, "*", 0)
        await message.answer(text, reply_markup=markup)

    @r.callback_query(F.data.regexp(r"^feed:([a-z]+|\*):\d+$"))
    async def feed_more(call: CallbackQuery) -> None:
        _, cat, offset = call.data.split(":")
        if cat != "*" and cat not in CATEGORIES:
            cat = "*"
        text, markup = await feed_page(call.from_user.id, cat, int(offset))
        await replace(call, text, markup)
        await call.answer()

    @r.callback_query(F.data == "fcat")
    async def feed_categories(call: CallbackQuery) -> None:
        await replace(call, "Какая работа интересует?", kb(*category_rows("feed:"), [btn("Все категории", "feed:*:0")]))
        await call.answer()

    @r.callback_query(F.data.regexp(r"^feed:[a-z]+$"))
    async def feed_category(call: CallbackQuery) -> None:
        cat = call.data.split(":")[1]
        text, markup = await feed_page(call.from_user.id, cat if cat in CATEGORIES else "*", 0)
        await replace(call, text, markup)
        await call.answer()

    @r.message(F.text == BTN_NEAR)
    async def near_hint(message: Message) -> None:
        # Сюда попадают, только если Telegram не прислал геопозицию (например, с компьютера).
        await message.answer("Пришлите геопозицию: 📎 → Геопозиция. С компьютера её отправить нельзя, "
                             "откройте бота на телефоне.")

    @r.message(StateFilter(None), F.location)
    async def near(message: Message) -> None:
        loc = message.location
        text, markup = await feed_page(message.from_user.id, "*", 0, loc.latitude, loc.longitude)
        await message.answer(text, reply_markup=markup)

    @r.callback_query(F.data.regexp(r"^near:-?[\d.]+:-?[\d.]+:\d+$"))
    async def near_more(call: CallbackQuery) -> None:
        _, lat, lng, offset = call.data.split(":")
        text, markup = await feed_page(call.from_user.id, "*", int(offset), float(lat), float(lng))
        await replace(call, text, markup)
        await call.answer()

    # --- карточка заявки и отклик -------------------------------------------------

    async def load(user_id: int, job_id: int):
        """Заявка и мой отклик на неё; None, если её не видно."""
        job = await pool.fetchrow(jobs_where("j.id = $2"), user_id, job_id)
        if not job:
            return None, None
        mine = await pool.fetchrow("SELECT id, status FROM responses WHERE job_id = $1 AND worker_id = $2",
                                   job_id, user_id)
        open_ = job["status"] == "open" and job["expires_at"] > datetime.now(timezone.utc) and not job["hidden_at"]
        if not (open_ or job["is_mine"] or mine):
            return None, None
        return job, mine

    def card_markup(job, mine):
        app_row = [app("Открыть в приложении", f"?job={job['id']}")]
        if job["is_mine"]:
            return kb([btn("⚙️ Управлять заявкой", f"mj:{job['id']}")], app_row)
        save = [btn("★ В избранном" if job["is_saved"] else "☆ В избранное", f"sv:{job['id']}")]
        if mine and mine["status"] in ("pending", "accepted"):
            return kb([btn("↩️ Отозвать отклик", f"wd:{mine['id']}")], save, app_row)
        if job["status"] != "open":
            return kb(save, app_row)
        return kb([btn("🙋 Откликнуться", f"ap:{job['id']}"), btn("✍️ С сообщением", f"apm:{job['id']}")],
                  save, app_row)

    def card_text(job, mine) -> str:
        text = job_card(job)
        if mine:
            text += f"\n\nВаш отклик: {STATUS[mine['status']]}"
        elif job["status"] != "open":
            text += "\n\nНабор закрыт."
        return text

    async def send_card(message: Message, user_id: int, job_id: int) -> None:
        job, mine = await load(user_id, job_id)
        if not job:
            await message.answer("Заявка закрыта или удалена. Посмотрите другие: /jobs")
            return
        await message.answer(card_text(job, mine), reply_markup=card_markup(job, mine))

    @r.callback_query(F.data.regexp(r"^job:\d+$"))
    async def show(call: CallbackQuery) -> None:
        await send_card(call.message, call.from_user.id, int(call.data[4:]))
        await call.answer()

    @r.callback_query(F.data.regexp(r"^sv:\d+$"))
    async def save(call: CallbackQuery) -> None:
        """Избранное: то же, что звёздочка в приложении."""
        job_id = int(call.data[3:])
        job, mine = await load(call.from_user.id, job_id)
        if not job:
            await call.answer("Заявка закрыта", show_alert=True)
            return
        if job["is_saved"]:
            await pool.execute("DELETE FROM saved_jobs WHERE user_id = $1 AND job_id = $2", call.from_user.id, job_id)
        elif await pool.fetchval("SELECT count(*) FROM saved_jobs WHERE user_id = $1", call.from_user.id) >= MAX_SAVED:
            await call.answer(f"В избранном уже {MAX_SAVED} заявок. Уберите старые.", show_alert=True)
            return
        else:
            await pool.execute("INSERT INTO saved_jobs (user_id, job_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                               call.from_user.id, job_id)
        job, mine = await load(call.from_user.id, job_id)
        try:
            await call.message.edit_reply_markup(reply_markup=card_markup(job, mine))
        except Exception:
            pass
        await call.answer("Убрано из избранного" if not job["is_saved"] else "Сохранено в избранное")

    async def do_respond(user_id: int, job_id: int, text: str | None) -> int:
        async with pool.acquire() as conn, conn.transaction():
            rid = await actions.respond(conn, job_id, user_id, text)
        await ensure_role(pool, user_id, "worker")
        return rid

    @r.callback_query(F.data.regexp(r"^ap:\d+$"))
    async def apply(call: CallbackQuery) -> None:
        try:
            rid = await do_respond(call.from_user.id, int(call.data[3:]), None)
        except actions.ActionError as e:
            await call.answer(e.detail, show_alert=True)
            return
        await note(call, "✅ Отклик отправлен. Когда заказчик ответит, я напишу.",
                   kb([btn("↩️ Отозвать отклик", f"wd:{rid}")]))
        await call.answer("Отклик отправлен")

    @r.callback_query(F.data.regexp(r"^apm:\d+$"))
    async def apply_with_message(call: CallbackQuery, state: FSMContext) -> None:
        job, mine = await load(call.from_user.id, int(call.data[4:]))
        if not job or job["status"] != "open":
            await call.answer("Набор на эту заявку закрыт", show_alert=True)
            return
        await state.set_state(RespondForm.message)
        await state.update_data(job_id=job["id"])
        await call.message.answer(f"Напишите заказчику «{esc(job['title'])}» пару слов: опыт, когда сможете "
                                  "приехать. Одним сообщением, до 500 знаков.",
                                  reply_markup=kb([btn("Отмена", "cancel")]))
        await call.answer()

    @r.message(RespondForm.message, ANSWER)
    async def apply_message(message: Message, state: FSMContext) -> None:
        if len(message.text) > 500:
            await message.answer(f"Длинновато: {len(message.text)} знаков из 500. Сократите, пожалуйста.")
            return
        job_id = (await state.get_data())["job_id"]
        await state.clear()
        try:
            rid = await do_respond(message.from_user.id, job_id, message.text)
        except actions.ActionError as e:
            await message.answer(e.detail)
            return
        await message.answer("✅ Отклик с сообщением отправлен. Когда заказчик ответит, я напишу.",
                             reply_markup=kb([btn("↩️ Отозвать отклик", f"wd:{rid}")]))

    @r.callback_query(F.data.regexp(r"^wd:\d+$"))
    async def withdraw(call: CallbackQuery) -> None:
        try:
            async with pool.acquire() as conn, conn.transaction():
                await actions.set_response_status(conn, int(call.data[3:]), call.from_user.id, "withdrawn")
        except actions.ActionError as e:
            await call.answer(e.detail, show_alert=True)
            return
        await note(call, "↩️ Отклик отозван")
        await call.answer("Отклик отозван")

    # --- мои отклики ------------------------------------------------------------

    @r.message(Command("responses"))
    @r.message(F.text == BTN_RESPONSES)
    async def responses(message: Message, state: FSMContext) -> None:
        await state.clear()
        rows = await pool.fetch(
            """SELECT r.id, r.status, j.id AS job_id, j.title, j.employer_id, e.first_name, e.username
               FROM responses r JOIN jobs j ON j.id = r.job_id JOIN users e ON e.tg_id = j.employer_id
               WHERE r.worker_id = $1 ORDER BY (r.status IN ('pending', 'accepted')) DESC, r.updated_at DESC
               LIMIT 10""",
            message.from_user.id,
        )
        if not rows:
            await message.answer("Откликов пока нет. Найдите заявку: /jobs",
                                 reply_markup=kb([btn(BTN_FIND, "feed:*:0")]))
            return
        lines = ["<b>Ваши отклики</b>"]
        buttons = []
        for i, row in enumerate(rows, start=1):
            line = f"{i}. {esc(row['title'])} — {STATUS[row['status']]}"
            if row["status"] == "accepted":
                line += f"\n    Заказчик: {events.contact_html(row['employer_id'], row['first_name'], row['username'])}"
            lines.append(line)
            buttons.append(btn(str(i), f"job:{row['job_id']}"))
        await message.answer("\n".join(lines) + "\n\nНажмите номер, чтобы открыть заявку.",
                             reply_markup=kb(buttons[:5], buttons[5:], [app("Все отклики", "?tab=responses")]))

    # --- подписки ---------------------------------------------------------------

    async def subs_view(user_id: int):
        rows = await pool.fetch("SELECT id, name, enabled FROM subscriptions WHERE user_id = $1 ORDER BY id", user_id)
        if rows:
            text = ("<b>Подписки</b>\nНовые заявки по ним приходят сюда. Нажмите на подписку, "
                    "чтобы выключить или включить её.")
        else:
            text = "<b>Подписок пока нет</b>\nПодпишитесь на категорию или на работу рядом, и новые заявки будут приходить сюда."
        rows_kb = [[btn(f"{'🔔' if s['enabled'] else '🔕'} {s['name']}"[:60], f"sub:t:{s['id']}"),
                    btn("🗑", f"sub:d:{s['id']}")] for s in rows]
        rows_kb.append([btn("➕ По категории", "sub:new"), btn("📍 Рядом с местом", "sub:near")])
        return text, kb(*rows_kb, [app("Подписка с фильтрами", "?tab=feed")])

    @r.message(Command("subs"))
    @r.message(F.text == BTN_SUBS)
    async def subs(message: Message, state: FSMContext) -> None:
        await state.clear()
        text, markup = await subs_view(message.from_user.id)
        await message.answer(text, reply_markup=markup)

    @r.callback_query(F.data.regexp(r"^sub:[td]:\d+$"))
    async def sub_change(call: CallbackQuery) -> None:
        _, kind, sid = call.data.split(":")
        if kind == "t":
            await pool.execute("UPDATE subscriptions SET enabled = NOT enabled WHERE id = $1 AND user_id = $2",
                               int(sid), call.from_user.id)
        else:
            await pool.execute("DELETE FROM subscriptions WHERE id = $1 AND user_id = $2", int(sid), call.from_user.id)
        text, markup = await subs_view(call.from_user.id)
        await replace(call, text, markup)
        await call.answer("Подписка удалена" if kind == "d" else None)

    async def can_subscribe(user_id: int) -> bool:
        n = await pool.fetchval("SELECT count(*) FROM subscriptions WHERE user_id = $1", user_id)
        return n < MAX_SUBSCRIPTIONS

    @r.callback_query(F.data == "sub:new")
    async def sub_new(call: CallbackQuery) -> None:
        await call.message.answer("На какую работу подписаться?", reply_markup=kb(*category_rows("subc:")))
        await call.answer()

    @r.callback_query(F.data.regexp(r"^subc:[a-z]+$"))
    async def sub_category(call: CallbackQuery) -> None:
        cat = call.data[5:]
        if cat not in CATEGORIES:
            await call.answer()
            return
        if not await can_subscribe(call.from_user.id):
            await call.answer(f"Можно не больше {MAX_SUBSCRIPTIONS} подписок", show_alert=True)
            return
        label, emoji = CATEGORIES[cat]
        await pool.execute("INSERT INTO subscriptions (user_id, name, categories) VALUES ($1, $2, $3)",
                           call.from_user.id, f"{emoji} {label}", [cat])
        await ensure_role(pool, call.from_user.id, "worker")
        text, markup = await subs_view(call.from_user.id)
        await replace(call, f"🔔 Готово: новые заявки «{label}» будут приходить сюда.\n\n" + text, markup)
        await call.answer("Подписка создана")

    @r.callback_query(F.data == "sub:near")
    async def sub_near(call: CallbackQuery, state: FSMContext) -> None:
        if not await can_subscribe(call.from_user.id):
            await call.answer(f"Можно не больше {MAX_SUBSCRIPTIONS} подписок", show_alert=True)
            return
        await state.set_state(SubForm.location)
        ask = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 Отправить, где я сейчас", request_location=True)]],
                                  resize_keyboard=True, one_time_keyboard=True)
        await call.message.answer(f"Пришлите точку: где вы сейчас или любое место через 📎 → Геопозиция. "
                                  f"Буду присылать заявки в радиусе {SUB_NEAR_KM} км.", reply_markup=ask)
        await call.answer()

    @r.message(SubForm.location, F.location)
    async def sub_near_point(message: Message, state: FSMContext) -> None:
        await state.clear()
        loc = message.location
        await pool.execute(
            "INSERT INTO subscriptions (user_id, name, location, radius_km) "
            "VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography, $5)",
            message.from_user.id, f"📍 Рядом ({SUB_NEAR_KM} км)", loc.longitude, loc.latitude, SUB_NEAR_KM,
        )
        await ensure_role(pool, message.from_user.id, "worker")
        await message.answer(f"🔔 Готово: заявки в {SUB_NEAR_KM} км от этой точки будут приходить сюда.",
                             reply_markup=MENU)

    @r.message(Command("stop"))
    async def stop(message: Message) -> None:
        await pool.execute("UPDATE subscriptions SET enabled = FALSE WHERE user_id = $1", message.from_user.id)
        await message.answer("Рассылка новых заявок выключена. События по вашим заявкам и откликам "
                             "по-прежнему будут приходить. Включить подписки: /subs")

    return r, send_card
