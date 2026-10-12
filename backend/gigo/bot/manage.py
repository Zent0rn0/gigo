"""Заказчик в боте: мои заявки, отклики на них, закрыть/отменить/повторить. Отзывы звёздами для обеих сторон."""

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from gigo import actions, config, events, rules
from gigo.bot import look
from gigo.bot.common import (ANSWER, BTN_MY, JOB_STATUS, STATUS, Kb, app, btn, job_card, note, num, rating_text,
                             replace)
from gigo.format import esc
from gigo.jobs_query import jobs_where, responses_where

MAX_RESPONSES_SHOWN = 10


class ReviewForm(StatesGroup):
    text = State()


def stars(n: int) -> str:
    return "★" * n + "☆" * (5 - n)


def make_router(settings: config.Settings, pool) -> Router:
    r = Router(name="manage")
    kb = Kb(settings)

    # --- список и карточка ------------------------------------------------------

    @r.message(Command("my"))
    @r.message(F.text == BTN_MY)
    async def my(message: Message, state: FSMContext) -> None:
        await state.clear()
        rows = await pool.fetch(
            jobs_where("j.employer_id = $1 AND j.hidden_at IS NULL AND j.created_at > now() - interval '30 days'",
                       "(j.status = 'open' AND j.expires_at > now()) DESC, j.created_at DESC") + " LIMIT 10",
            message.from_user.id,
        )
        if not rows:
            await look.show(message, "📋 <b>Ваши заявки</b>\n\n<i>Заявок пока нет.</i> Создайте первую за минуту.",
                            kb([btn("➕ Создать заявку", "nj:start", "success")]), banner="my")
            return
        lines = ["📋 <b>Ваши заявки</b>"]
        for i, j in enumerate(rows, start=1):
            if j["status"] == "open" and j["expires_at"] <= datetime.now(timezone.utc):
                state_text = "⌛ срок вышел"
            else:
                state_text = JOB_STATUS[j["status"]]
            if j["pending_count"]:
                state_text += f" · 🙋 новых откликов: {j['pending_count']}"
            if j["accepted_count"]:
                state_text += f" · принято {j['accepted_count']} из {j['workers_needed']}"
            lines.append(f"{num(i)} <b>{esc(j['title'])}</b>\n{state_text}")
        numbers = [btn(str(i), f"mj:{j['id']}") for i, j in enumerate(rows, start=1)]
        await look.show(message, "\n\n".join(lines) + "\n\n👇 <i>Нажмите номер, чтобы посмотреть отклики и управлять "
                                 "заявкой.</i>",
                        kb(numbers[:5], numbers[5:], [btn("➕ Новая заявка", "nj:start")]), banner="my")

    async def manage_view(user_id: int, job_id: int):
        job = await pool.fetchrow(jobs_where("j.id = $2 AND j.employer_id = $1"), user_id, job_id)
        if not job:
            return None, None
        expired = job["expires_at"] <= datetime.now(timezone.utc)
        status = "⌛ срок вышел" if job["status"] == "open" and expired else JOB_STATUS[job["status"]]
        if job["hidden_at"]:
            status = "🚫 скрыта модератором"
        text = job_card(job) + f"\n\n<b>Статус:</b> {status}\n<b>Отклики:</b> ждут ответа {job['pending_count']}, " \
                               f"принято {job['accepted_count']}"
        rows = []
        if job["responses_count"] or job["pending_count"]:
            rows.append([btn(f"👥 Отклики ({job['responses_count']})", f"rl:{job_id}")])
        if job["status"] == "open" and not expired:
            rows.append([btn("🔒 Закрыть набор", f"jc:{job_id}"), btn("❌ Отменить", f"jx:{job_id}", "danger")])
        elif job["status"] == "closed" and not expired and not job["hidden_at"]:
            rows.append([btn("🔓 Открыть набор снова", f"jo:{job_id}")])
        if not job["hidden_at"]:
            rows.append([btn("🔁 Повторить на другой день", f"jr:{job_id}")])
        rows.append([app("Открыть в приложении", f"?job={job_id}")])
        return text, kb(*rows)

    @r.callback_query(F.data.regexp(r"^mj:\d+$"))
    async def manage(call: CallbackQuery) -> None:
        text, markup = await manage_view(call.from_user.id, int(call.data[3:]))
        if not text:
            await call.answer("Заявка не найдена", show_alert=True)
            return
        await call.message.answer(text, reply_markup=markup)
        await call.answer()

    async def set_status(call: CallbackQuery, status: str, done: str) -> None:
        job_id = int(call.data.split(":")[1])  # jc:42, jo:42, jxy:42
        try:
            async with pool.acquire() as conn, conn.transaction():
                await actions.set_job_status(conn, job_id, call.from_user.id, status)
        except actions.ActionError as e:
            await call.answer(e.detail, show_alert=True)
            return
        text, markup = await manage_view(call.from_user.id, job_id)
        await replace(call, text, markup)
        await call.answer(done)

    @r.callback_query(F.data.regexp(r"^jc:\d+$"))
    async def close(call: CallbackQuery) -> None:
        await set_status(call, "closed", "Набор закрыт. Ожидающим откликам я сообщил.")

    @r.callback_query(F.data.regexp(r"^jo:\d+$"))
    async def reopen(call: CallbackQuery) -> None:
        await set_status(call, "open", "Набор снова открыт")

    @r.callback_query(F.data.regexp(r"^jx:\d+$"))
    async def cancel_ask(call: CallbackQuery) -> None:
        job_id = call.data[3:]
        await call.message.edit_reply_markup(reply_markup=kb(
            [btn("Да, отменить заявку", f"jxy:{job_id}", "danger")], [btn("Нет, оставить", f"mjr:{job_id}")]))
        await call.answer("Всем, кто откликнулся, придёт сообщение об отмене")

    @r.callback_query(F.data.regexp(r"^jxy:\d+$"))
    async def cancel(call: CallbackQuery) -> None:
        await set_status(call, "cancelled", "Заявка отменена")

    @r.callback_query(F.data.regexp(r"^mjr:\d+$"))
    async def manage_refresh(call: CallbackQuery) -> None:
        text, markup = await manage_view(call.from_user.id, int(call.data[4:]))
        if text:
            await replace(call, text, markup)
        await call.answer()

    # --- повтор ------------------------------------------------------------------

    @r.callback_query(F.data.regexp(r"^jr:\d+$"))
    async def repeat_ask(call: CallbackQuery) -> None:
        job_id = call.data[3:]
        await call.message.answer("На какой день повторить? Условия, место и время останутся прежними.",
                                  reply_markup=kb([btn("Сегодня", f"jrd:{job_id}:0"), btn("Завтра", f"jrd:{job_id}:1"),
                                                   btn("Послезавтра", f"jrd:{job_id}:2")]))
        await call.answer()

    @r.callback_query(F.data.regexp(r"^jrd:\d+:[0-6]$"))
    async def repeat(call: CallbackQuery) -> None:
        _, job_id, shift = call.data.split(":")
        day = datetime.now(rules.MSK).date() + timedelta(days=int(shift))
        try:
            async with pool.acquire() as conn, conn.transaction():
                new_id = await actions.repeat_job(conn, int(job_id), call.from_user.id, day)
        except actions.ActionError as e:
            await call.answer(e.detail, show_alert=True)
            return
        await note(call, f"🔁 Заявка на {day:%d.%m} опубликована")
        text, markup = await manage_view(call.from_user.id, new_id)
        await call.message.answer(text, reply_markup=markup)
        await call.answer("Опубликовано")

    # --- отклики на мою заявку ------------------------------------------------------

    @r.callback_query(F.data.regexp(r"^rl:\d+$"))
    async def responses_list(call: CallbackQuery) -> None:
        job_id = int(call.data[3:])
        owner = await pool.fetchval("SELECT employer_id FROM jobs WHERE id = $1", job_id)
        if owner != call.from_user.id:
            await call.answer("Заявка не найдена", show_alert=True)
            return
        rows = await pool.fetch(
            responses_where("r.job_id = $2 AND r.status IN ('pending', 'accepted')",
                            "(r.status = 'pending') DESC, r.created_at"),
            call.from_user.id, job_id)
        if not rows:
            await call.answer("Ждущих ответа и принятых откликов нет", show_alert=True)
            return
        await call.answer()
        for resp in rows[:MAX_RESPONSES_SHOWN]:
            text = f"🙋 <b>{esc(resp['worker_name'] or 'Исполнитель')}</b>\n" \
                   f"{rating_text(resp['worker_rating'], resp['worker_reviews'])}"
            if resp["worker_about"]:
                text += f"\n<i>{esc(resp['worker_about'][:200])}</i>"
            if resp["message"]:
                text += f"\n<blockquote>«{esc(resp['message'])}»</blockquote>"
            text += f"\n{STATUS[resp['status']]}"
            if resp["status"] == "accepted":
                text += "\nКонтакт: " + events.contact_html(resp["worker_id"], resp["worker_name"],
                                                            resp["worker_username"])
                markup = None
            else:
                markup = kb([btn("✅ Принять", f"acc:{resp['id']}", "success"),
                             btn("✖️ Отклонить", f"rej:{resp['id']}", "danger")])
            await call.message.answer(text, reply_markup=markup)
        if len(rows) > MAX_RESPONSES_SHOWN:
            await call.message.answer(f"И ещё {len(rows) - MAX_RESPONSES_SHOWN}: все отклики в приложении.",
                                      reply_markup=kb([app("Все отклики", f"?job={job_id}")]))

    # --- отзывы звёздами -----------------------------------------------------------

    @r.callback_query(F.data.regexp(r"^rv:\d+:[1-5]$"))
    async def review(call: CallbackQuery, state: FSMContext) -> None:
        _, rid, n = call.data.split(":")
        try:
            async with pool.acquire() as conn:
                await actions.save_review(conn, int(rid), call.from_user.id, int(n), None, keep_text=True)
        except actions.ActionError as e:
            await call.answer(e.detail, show_alert=True)
            return
        await state.set_state(ReviewForm.text)
        await state.update_data(response_id=int(rid), rating=int(n))
        await note(call, f"Ваша оценка: {stars(int(n))}. Спасибо!",
                   kb([btn("Изменить оценку", f"rvc:{rid}")]))
        await call.message.answer("Добавьте пару слов к отзыву одним сообщением или нажмите «Готово».",
                                  reply_markup=kb([btn("Готово", "cancel")]))
        await call.answer("Оценка сохранена")

    @r.callback_query(F.data.regexp(r"^rvc:\d+$"))
    async def review_change(call: CallbackQuery) -> None:
        rid = call.data[4:]
        await call.message.edit_reply_markup(reply_markup=kb([btn(str(i) + "★", f"rv:{rid}:{i}") for i in range(1, 6)]))
        await call.answer()

    @r.message(ReviewForm.text, ANSWER)
    async def review_text(message: Message, state: FSMContext) -> None:
        if len(message.text) > 1000:
            await message.answer(f"Длинновато: {len(message.text)} знаков из 1000.")
            return
        d = await state.get_data()
        await state.clear()
        try:
            async with pool.acquire() as conn:
                await actions.save_review(conn, d["response_id"], message.from_user.id, d["rating"], message.text)
        except actions.ActionError as e:
            await message.answer(e.detail)
            return
        await message.answer("Отзыв сохранён. Спасибо, это помогает другим выбирать!")

    return r
