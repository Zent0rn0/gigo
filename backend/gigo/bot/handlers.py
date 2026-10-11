"""Команды и кнопки бота."""

import logging
import re

from aiogram import Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BotCommand, CallbackQuery, Message

from gigo import actions, config
from gigo.bot.loops import app_button, keyboard
from gigo.format import esc

log = logging.getLogger("gigo.bot")

COMMANDS = [
    BotCommand(command="start", description="Открыть Gigo"),
    BotCommand(command="new", description="Создать заявку"),
    BotCommand(command="my", description="Мои заявки и отклики на них"),
    BotCommand(command="responses", description="Мои отклики"),
    BotCommand(command="subs", description="Подписки на новые заявки"),
    BotCommand(command="stop", description="Выключить рассылку новых заявок"),
    BotCommand(command="help", description="Как это работает"),
]

HELP = (
    "<b>Gigo: подработка в Москве без посредников</b>\n\n"
    "<b>Ищете людей?</b> Создайте заявку: что сделать, где, когда и сколько платите. Отклики придут сюда, "
    "принять или отклонить можно прямо в чате. После принятия вы увидите контакт исполнителя.\n\n"
    "<b>Ищете подработку?</b> Смотрите заявки в ленте и на карте, откликайтесь в один тап. "
    "Подпишитесь на фильтр, и новые заявки будут приходить сюда.\n\n"
    "<b>Безопасность.</b> Не платите за «оформление», форму или обучение и не передавайте данные карт и коды из СМС. "
    "Подозрительную заявку отправьте модератору кнопкой «Пожаловаться» в приложении.\n\n"
    "/new создать заявку · /my мои заявки · /responses мои отклики · /subs подписки"
)

STATUS = {"pending": "⏳ ждёт ответа", "accepted": "✅ принят", "rejected": "✖️ отклонён", "withdrawn": "↩️ отозван"}
_START_PAYLOAD = re.compile(r"^(job_\d+|tab_[a-z]+)$")


def make_dispatcher(settings: config.Settings, pool) -> Dispatcher:
    dp = Dispatcher()
    admins = set(settings.admin_ids)

    async def remember(user) -> bool:
        """Запоминает пользователя; False, если он заблокирован."""
        row = await pool.fetchrow(
            """INSERT INTO users (tg_id, username, first_name) VALUES ($1, $2, $3)
               ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username, first_name = EXCLUDED.first_name,
                   bot_blocked = FALSE, last_seen_at = now()
               RETURNING banned_at""",
            user.id, user.username, (user.first_name or "")[:64] or None,
        )
        return row["banned_at"] is None

    def open_app(text: str, path: str = ""):
        return app_button(settings, text, path)

    @dp.message(CommandStart())
    async def start(message: Message, command: CommandObject) -> None:
        if not await remember(message.from_user):
            await message.answer("Аккаунт заблокирован за нарушение правил Gigo.")
            return
        payload = command.args or ""
        if _START_PAYLOAD.match(payload):
            path = f"?job={payload[4:]}" if payload.startswith("job_") else f"?tab={payload[4:]}"
            await message.answer("Открываю 👇", reply_markup=open_app("Открыть", path))
            return
        await message.answer(HELP, reply_markup=open_app("Открыть Gigo"))

    @dp.message(Command("help"))
    async def help_(message: Message) -> None:
        await message.answer(HELP, reply_markup=open_app("Открыть Gigo"))

    @dp.message(Command("new"))
    async def new(message: Message) -> None:
        await message.answer("Заполните заявку в приложении: это займёт минуту.",
                             reply_markup=open_app("Создать заявку", "?tab=create"))

    @dp.message(Command("my"))
    async def my(message: Message) -> None:
        rows = await pool.fetch(
            """SELECT j.id, j.title, j.status, j.expires_at > now() AS active,
                      count(r.*) FILTER (WHERE r.status = 'pending') AS pending,
                      count(r.*) FILTER (WHERE r.status = 'accepted') AS accepted
               FROM jobs j LEFT JOIN responses r ON r.job_id = j.id
               WHERE j.employer_id = $1 AND j.status = 'open' AND j.hidden_at IS NULL
               GROUP BY j.id ORDER BY j.created_at DESC LIMIT 10""",
            message.from_user.id,
        )
        if not rows:
            await message.answer("Открытых заявок нет.", reply_markup=open_app("Создать заявку", "?tab=create"))
            return
        lines = ["<b>Ваши открытые заявки</b>"]
        rows_kb = []
        for r in rows:
            state = f"новых откликов: {r['pending']}" if r["pending"] else "новых откликов нет"
            if r["accepted"]:
                state += f", принято: {r['accepted']}"
            if not r["active"]:
                state = "срок вышел"
            lines.append(f"• {esc(r['title'])} — {state}")
            rows_kb.append([{"text": r["title"][:40], "path": f"?job={r['id']}"}])
        await message.answer("\n".join(lines), reply_markup=keyboard(settings, rows_kb))

    @dp.message(Command("responses"))
    async def responses(message: Message) -> None:
        rows = await pool.fetch(
            """SELECT r.status, j.id, j.title FROM responses r JOIN jobs j ON j.id = r.job_id
               WHERE r.worker_id = $1 ORDER BY r.updated_at DESC LIMIT 10""",
            message.from_user.id,
        )
        if not rows:
            await message.answer("Откликов пока нет. Найдите заявку в ленте.",
                                 reply_markup=open_app("Открыть ленту", "?tab=feed"))
            return
        lines = ["<b>Ваши отклики</b>"] + [f"• {esc(r['title'])} — {STATUS[r['status']]}" for r in rows]
        await message.answer("\n".join(lines), reply_markup=open_app("Все отклики", "?tab=responses"))

    @dp.message(Command("subs"))
    async def subs(message: Message) -> None:
        rows = await pool.fetch(
            "SELECT name, enabled FROM subscriptions WHERE user_id = $1 ORDER BY id", message.from_user.id
        )
        if not rows:
            text = "Подписок пока нет. Откройте ленту, настройте фильтр и нажмите «Подписаться»."
        else:
            text = "Ваши подписки:\n" + "\n".join(f"{'🔔' if r['enabled'] else '🔕'} {esc(r['name'])}" for r in rows)
        await message.answer(text, reply_markup=open_app("Управлять подписками", "?tab=profile"))

    @dp.message(Command("stop"))
    async def stop(message: Message) -> None:
        await pool.execute("UPDATE subscriptions SET enabled = FALSE WHERE user_id = $1", message.from_user.id)
        await message.answer("Рассылка новых заявок выключена. События по вашим заявкам и откликам "
                             "по-прежнему будут приходить. Подписки включаются в приложении.")

    # --- кнопки под сообщениями -------------------------------------------------

    async def finish(call: CallbackQuery, note: str) -> None:
        """Убирает кнопки действия и дописывает итог в сообщение."""
        try:
            await call.message.edit_text(f"{call.message.html_text}\n\n<b>{note}</b>",
                                         reply_markup=keyboard(settings, _app_rows(call)))
        except Exception as e:  # сообщение могло быть старым или уже изменённым
            log.info("не удалось обновить сообщение: %s", e)
        await call.answer(note)

    def _app_rows(call: CallbackQuery) -> list[list[dict]]:
        """Оставляет кнопки, открывающие приложение."""
        kb = call.message.reply_markup.inline_keyboard if call.message and call.message.reply_markup else []
        rows = []
        for row in kb:
            for b in row:
                if b.web_app:
                    path = b.web_app.url.split("/", 3)[-1] if settings.webapp_url else ""
                    rows.append([{"text": b.text, "path": path if path.startswith("?") else ""}])
        return rows

    @dp.callback_query(F.data.regexp(r"^(acc|rej):\d+$"))
    async def decide(call: CallbackQuery) -> None:
        kind, rid = call.data.split(":")
        status = "accepted" if kind == "acc" else "rejected"
        try:
            async with pool.acquire() as conn, conn.transaction():
                await actions.set_response_status(conn, int(rid), call.from_user.id, status)
        except actions.ActionError as e:
            await call.answer(e.detail, show_alert=True)
            return
        await finish(call, "✅ Принят. Контакт исполнителя пришёл отдельным сообщением." if status == "accepted"
                     else "✖️ Отклонён")

    @dp.callback_query(F.data.regexp(r"^(hide|ok|ban):\d+$"))
    async def moderate(call: CallbackQuery) -> None:
        if call.from_user.id not in admins:
            await call.answer("Только для модераторов", show_alert=True)
            return
        kind, target = call.data.split(":")
        try:
            async with pool.acquire() as conn, conn.transaction():
                if kind == "hide":
                    await actions.hide_job(conn, int(target))
                    note = "🚫 Заявка скрыта"
                elif kind == "ok":
                    await actions.dismiss_reports(conn, int(target))
                    note = "👌 Жалобы отклонены"
                else:
                    n = await actions.ban_user(conn, int(target))
                    note = f"⛔ Автор заблокирован, скрыто заявок: {n}"
        except actions.ActionError as e:
            await call.answer(e.detail, show_alert=True)
            return
        await finish(call, note)

    # --- команды модератора ---------------------------------------------------------

    @dp.message(Command("ban", "unban", "stats"), F.from_user.id.in_(admins))
    async def admin(message: Message, command: CommandObject) -> None:
        if command.command == "stats":
            s = await pool.fetchrow(
                """SELECT (SELECT count(*) FROM users) AS users,
                          (SELECT count(*) FROM users WHERE role = 'employer') AS employers,
                          (SELECT count(*) FROM users WHERE role = 'worker') AS workers,
                          (SELECT count(*) FROM jobs WHERE status = 'open' AND expires_at > now()
                                                           AND hidden_at IS NULL) AS open_jobs,
                          (SELECT count(*) FROM jobs WHERE created_at > now() - interval '1 day') AS jobs_day,
                          (SELECT count(*) FROM responses WHERE created_at > now() - interval '1 day') AS resp_day,
                          (SELECT count(*) FROM reports WHERE resolved_at IS NULL) AS reports""")
            await message.answer(
                f"Пользователей: {s['users']} (заказчиков {s['employers']}, исполнителей {s['workers']})\n"
                f"Открытых заявок: {s['open_jobs']}\nЗа сутки: заявок {s['jobs_day']}, откликов {s['resp_day']}\n"
                f"Жалоб ждут решения: {s['reports']}")
            return
        parts = (command.args or "").split(maxsplit=1)
        if not parts or not parts[0].isdigit():
            await message.answer(f"Формат: /{command.command} &lt;id пользователя&gt; [причина]")
            return
        uid = int(parts[0])
        try:
            async with pool.acquire() as conn, conn.transaction():
                if command.command == "ban":
                    n = await actions.ban_user(conn, uid, parts[1] if len(parts) > 1 else "нарушение правил")
                    await message.answer(f"Заблокирован, скрыто заявок: {n}")
                else:
                    await actions.unban_user(conn, uid)
                    await message.answer("Разблокирован")
        except actions.ActionError as e:
            await message.answer(e.detail)

    @dp.message()
    async def other(message: Message) -> None:
        await message.answer("Заявки и отклики в приложении 👇 Команды: /help",
                             reply_markup=open_app("Открыть Gigo"))

    return dp
