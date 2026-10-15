"""Бот: команды, меню и кнопки. Через бота можно и создать заявку, и откликнуться, без Mini App."""

import logging
import re

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, CallbackQuery, Message

from gigo import actions, config, i18n
from gigo.bot import browse, create, look, manage, safety
from gigo.bot.common import Kb, UserMiddleware, btn, menu, note, replace
from gigo.bot.loops import app_button, keyboard
from gigo.i18n import N_, tr

log = logging.getLogger("gigo.bot")

# Описания — русские ключи: список команд собирается на нужном языке через commands().
COMMANDS = [
    ("start", N_("Меню")),
    ("jobs", N_("Найти работу")),
    ("new", N_("Создать заявку")),
    ("my", N_("Мои заявки и отклики на них")),
    ("responses", N_("Мои отклики")),
    ("subs", N_("Подписки на новые заявки")),
    ("stop", N_("Выключить рассылку новых заявок")),
    ("cancel", N_("Прервать текущее действие")),
    ("lang", N_("Язык / Language")),
    ("help", N_("Как это работает")),
]


def commands() -> list[BotCommand]:
    """Меню команд на текущем языке."""
    return [BotCommand(command=c, description=tr(d)) for c, d in COMMANDS]

# Русские ключи: показывать через tr(HELP), tr(WELCOME).
HELP = N_(
    "💜 <b>Gigo: подработка в Москве без посредников</b>\n\n"
    "👷 <b>Ищете людей?</b>\n"
    "<blockquote>/new · заявка за минуту прямо здесь\n"
    "/my · ваши заявки: отклики, закрыть набор, повторить на другой день\n"
    "Отклики приходят сюда, принять или отклонить можно в один тап, после этого вы получите контакт.</blockquote>\n\n"
    "🔎 <b>Ищете подработку?</b>\n"
    "<blockquote>/jobs · свежие заявки, отклик в один тап\n"
    "📍 пришлите геопозицию, и я покажу работу рядом\n"
    "/subs · подписки: новые заявки будут приходить сами\n"
    "/responses · ваши отклики и контакты заказчиков</blockquote>\n\n"
    "🛡 <b>Безопасность</b>\n"
    "<blockquote>Не платите за «оформление», форму или обучение и не передавайте данные карт и коды из СМС. "
    "Подозрительную заявку отправьте модератору кнопкой «Пожаловаться» в приложении.</blockquote>\n\n"
    "<i>Всё то же самое есть в приложении: кнопка «Gigo» слева от поля ввода.</i>\n"
    "🌐 Язык / Language: /lang"
)

WELCOME = N_(
    "💜 <b>Привет! Это Gigo</b>\n"
    "<i>Подработка в Москве без посредников</i>\n\n"
    "📝 Заказчики публикуют заявки\n"
    "🙋 Исполнители откликаются в один тап\n"
    "🤝 После выбора вы получаете контакты друг друга\n"
    "⭐ После работы оставляете отзывы\n\n"
    "Всё можно делать прямо в этом чате, меню внизу.\n\n"
    "<b>Что вы ищете?</b>"
)

_START_PAYLOAD = re.compile(r"^(job_\d{1,18}|tab_[a-z]{1,20})$")


def make_dispatcher(settings: config.Settings, pool) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    safety.install(dp, pool)
    dp.message.outer_middleware(UserMiddleware(pool))
    dp.callback_query.outer_middleware(UserMiddleware(pool))
    admins = set(settings.admin_ids)
    kb = Kb(settings)
    browse_router, send_card = browse.make_router(settings, pool)
    main = Router(name="main")
    dp.include_routers(main, create.make_router(settings, pool), browse_router, manage.make_router(settings, pool))
    tail = Router(name="tail")  # то, что не подошло ни одному обработчику
    dp.include_router(tail)

    def open_app(text: str, path: str = ""):
        return app_button(settings, text, path)

    @main.message(CommandStart())
    async def start(message: Message, command: CommandObject, state: FSMContext, role: str | None = None) -> None:
        await state.clear()
        payload = command.args or ""
        if _START_PAYLOAD.match(payload):
            if payload.startswith("job_"):
                await send_card(message, message.from_user.id, int(payload[4:]))
            else:
                await message.answer(tr("Открываю 👇"), reply_markup=open_app(tr("Открыть"), f"?tab={payload[4:]}"))
            return
        if role is None:
            await message.answer("👋", reply_markup=menu())
            await look.show(message, tr(WELCOME), kb([btn(tr("🔎 Ищу подработку"), "role:worker", "primary")],
                                                     [btn(tr("👷 Ищу исполнителей"), "role:employer", "primary")]),
                            banner="welcome")
            return
        await look.show(message, tr("💜 <b>С возвращением в Gigo!</b>\n\nМеню внизу 👇 Подробнее: /help"), menu(),
                        banner="welcome")

    @main.callback_query(F.data.regexp(r"^role:(worker|employer)$"))
    async def choose_role(call: CallbackQuery, state: FSMContext) -> None:
        role = call.data[5:]
        await pool.execute("UPDATE users SET role = $2 WHERE tg_id = $1", call.from_user.id, role)
        await call.answer()
        if role == "worker":
            await note(call, tr("Ищу подработку"), kb([btn(tr("🔎 Смотреть заявки"), "feed:*:0")],
                                                      [btn(tr("🔔 Подписаться на новые"), "sub:new")]))
        else:
            await note(call, tr("Ищу исполнителей"), kb([btn(tr("➕ Создать первую заявку"), "nj:start")]))

    @main.message(Command("help"))
    async def help_(message: Message) -> None:
        await look.show(message, tr(HELP), menu(), banner="help")

    @main.message(Command("menu"))
    async def menu_cmd(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(tr("Меню внизу 👇"), reply_markup=menu())

    @main.message(Command("lang"))
    async def lang_cmd(message: Message) -> None:
        items = [btn(f"{i18n.FLAGS.get(code, '🌐')} {name}", f"lang:{code}") for code, name in i18n.LANGUAGES.items()]
        await message.answer("🌐 " + tr("Выберите язык"), reply_markup=kb(*[items[i:i + 2]
                                                                           for i in range(0, len(items), 2)]))

    @main.callback_query(F.data.startswith("lang:"))
    async def set_lang(call: CallbackQuery) -> None:
        code = call.data[5:]
        if code not in i18n.LANGUAGES:
            await call.answer(tr("Эта кнопка устарела. Начните заново из меню."), show_alert=True)
            return
        await pool.execute("UPDATE users SET lang = $2 WHERE tg_id = $1", call.from_user.id, code)
        i18n.set_lang(code)
        await call.answer()
        await replace(call, "✅ " + tr("Язык: {lang}", lang=f"{i18n.FLAGS.get(code, '🌐')} {i18n.LANGUAGES[code]}"))
        await call.message.answer(tr("Меню внизу 👇"), reply_markup=menu())
        try:  # команды в меню Telegram — тоже на выбранном языке, только для этого человека
            await call.bot.set_my_commands(commands(), scope=BotCommandScopeChat(chat_id=call.from_user.id))
        except Exception as e:
            log.info("не удалось обновить команды для %s: %r", call.from_user.id, e)

    @main.message(Command("cancel"))
    async def cancel_cmd(message: Message, state: FSMContext) -> None:
        had = await state.get_state()
        await state.clear()
        await message.answer(tr("Отменил.") if had else tr("Нечего отменять."), reply_markup=menu())

    @main.callback_query(F.data == "cancel")
    async def cancel_btn(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer(tr("Готово"))

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
        """Оставляет кнопки, открывающие приложение или список откликов."""
        kb = call.message.reply_markup.inline_keyboard if call.message and call.message.reply_markup else []
        rows = []
        for row in kb:
            for b in row:
                if b.callback_data and b.callback_data.startswith(("rl:", "mj:", "job:")):
                    rows.append([{"text": b.text, "data": b.callback_data}])
                elif b.web_app:
                    path = b.web_app.url.split("/", 3)[-1] if settings.webapp_url else ""
                    rows.append([{"text": b.text, "path": path if path.startswith("?") else ""}])
        return rows

    @main.callback_query(F.data.regexp(r"^(acc|rej):\d+$"))
    async def decide(call: CallbackQuery) -> None:
        kind, rid = call.data.split(":")
        status = "accepted" if kind == "acc" else "rejected"
        try:
            async with pool.acquire() as conn, conn.transaction():
                await actions.set_response_status(conn, int(rid), call.from_user.id, status)
        except actions.ActionError as e:
            await call.answer(e.detail, show_alert=True)
            return
        await finish(call, tr("✅ Принят. Контакт исполнителя пришёл отдельным сообщением.") if status == "accepted"
                     else tr("✖️ Отклонён"))

    @main.callback_query(F.data.regexp(r"^(hide|ok|ban):\d+$"))
    async def moderate(call: CallbackQuery) -> None:
        if call.from_user.id not in admins:
            await call.answer(tr("Только для модераторов"), show_alert=True)
            return
        kind, target = call.data.split(":")
        try:
            async with pool.acquire() as conn, conn.transaction():
                if kind == "hide":
                    await actions.hide_job(conn, int(target))
                    note = tr("🚫 Заявка скрыта")
                elif kind == "ok":
                    await actions.dismiss_reports(conn, int(target))
                    note = tr("👌 Жалобы отклонены")
                else:
                    n = await actions.ban_user(conn, int(target))
                    note = tr("⛔ Автор заблокирован, скрыто заявок: {n}", n=n)
        except actions.ActionError as e:
            await call.answer(e.detail, show_alert=True)
            return
        await finish(call, note)

    # --- команды модератора ---------------------------------------------------------

    @main.message(Command("ban", "unban", "stats"), F.from_user.id.in_(admins))
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
            await message.answer(tr(
                "Пользователей: {users} (заказчиков {employers}, исполнителей {workers})\n"
                "Открытых заявок: {open_jobs}\nЗа сутки: заявок {jobs_day}, откликов {resp_day}\n"
                "Жалоб ждут решения: {reports}", **dict(s)))
            return
        parts = (command.args or "").split(maxsplit=1)
        if not parts or not (parts[0].isascii() and parts[0].isdigit()) or not 0 < int(parts[0]) < 2**63:
            await message.answer(tr("Формат: /{command} &lt;id пользователя&gt; [причина]", command=command.command))
            return
        uid = int(parts[0])
        try:
            async with pool.acquire() as conn, conn.transaction():
                if command.command == "ban":
                    n = await actions.ban_user(conn, uid, parts[1] if len(parts) > 1 else "нарушение правил")
                    await message.answer(tr("Заблокирован, скрыто заявок: {n}", n=n))
                else:
                    await actions.unban_user(conn, uid)
                    await message.answer(tr("Разблокирован"))
        except actions.ActionError as e:
            await message.answer(e.detail)

    @tail.message()
    async def other(message: Message, state: FSMContext) -> None:
        if await state.get_state():
            await message.answer(tr("Жду ответ на вопрос выше. Прервать: /cancel"))
            return
        await message.answer(tr("Не понял. Выберите действие в меню внизу или /help."), reply_markup=menu())

    @tail.callback_query()
    async def stale(call: CallbackQuery) -> None:
        await call.answer(tr("Эта кнопка устарела. Начните заново из меню."), show_alert=True)

    return dp
