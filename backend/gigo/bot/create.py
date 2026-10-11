"""Заказчик в боте: заявка в диалоге, шаг за шагом, без Mini App."""

import re
from datetime import date, datetime, time, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from gigo import actions, config, rules
from gigo.bot.common import ANSWER, BTN_NEW, MENU, Kb, app, btn, category_rows, ensure_role
from gigo.categories import CATEGORIES, PAY_UNITS, SCAM_FLAGS
from gigo.format import esc, job_message
from gigo.geo import Geocoder

NEAREST_METRO_M = 1500
_TIME = re.compile(r"^\s*(\d{1,2})(?:\s*[:.\-\s]\s*(\d{2}))?\s*$")
_DATE = re.compile(r"^\s*(\d{1,2})[./](\d{1,2})\s*$")
_AMOUNT = re.compile(r"^\s*(\d[\d\s]*)")
_NUMBER = re.compile(r"^\s*(\d+(?:[.,]\d+)?)")
_METRO_PREFIX = re.compile(r"^\s*(?:м\.|метро|ст\.? ?м\.?)\s*", re.I)


class NewJobForm(StatesGroup):
    category = State()
    title = State()
    unit = State()
    amount = State()
    day = State()
    time = State()
    duration = State()
    place = State()
    workers = State()
    description = State()
    confirm = State()


CANCEL = btn("✖️ Отмена", "cancel")


def parse_time(text: str) -> time | None:
    m = _TIME.match(text)
    if not m:
        return None
    h, mm = int(m[1]), int(m[2] or 0)
    return time(h, mm) if h < 24 and mm < 60 else None


def parse_day(text: str, today: date) -> date | None:
    m = _DATE.match(text)
    if not m:
        return None
    try:
        day = date(today.year, int(m[2]), int(m[1]))
    except ValueError:
        return None
    return day if day >= today else day.replace(year=today.year + 1)


def parse_amount(text: str) -> int | None:
    m = _AMOUNT.match(text)
    if not m:
        return None
    value = int(re.sub(r"\s", "", m[1]))
    return value if 0 < value <= 1_000_000 else None


def parse_number(text: str) -> float | None:
    m = _NUMBER.match(text)
    return float(m[1].replace(",", ".")) if m else None


def preview(d: dict) -> str:
    per_hour, estimated = rules.pay_per_hour(d["pay_amount"], d["pay_unit"], d.get("duration_hours"))
    day = date.fromisoformat(d["starts_on"]) if d.get("starts_on") else None
    at = time.fromisoformat(d["start_time"]) if d.get("start_time") else None
    job = {
        "category": d["category"], "title": d["title"], "pay_per_hour": per_hour, "pay_estimated": estimated,
        "pay_total": rules.pay_total(d["pay_amount"], d["pay_unit"], d.get("duration_hours")),
        "pay_amount": d["pay_amount"], "pay_unit": d["pay_unit"], "pay_timing": None,
        "starts_on": day, "starts_at": rules.starts_at(day, at), "duration_hours": d.get("duration_hours"),
        "address": d.get("address") or ("точка на карте" if d.get("lat") else None),
    }
    lines = [job_message(job, d.get("metro_name"))]
    if d.get("address") and d.get("metro_name"):
        lines.append(f"🏠 {esc(d['address'])}")
    lines.append(f"👥 Нужно: {d['workers_needed']}")
    if d.get("description"):
        lines.append(f"\n{esc(d['description'])}")
    return "\n".join(lines)


def make_router(settings: config.Settings, pool) -> Router:
    r = Router(name="create")
    kb = Kb(settings)
    geocoder = Geocoder(settings.yandex_geocoder_key, pool)

    async def chosen(call: CallbackQuery, text: str) -> None:
        """Убирает кнопки шага и оставляет в сообщении выбранное значение."""
        try:
            await call.message.edit_text(f"{call.message.html_text}\n<b>→ {esc(text)}</b>", reply_markup=None)
        except Exception:
            pass
        try:
            await call.answer()
        except Exception:  # уже ответили
            pass

    # --- шаги -------------------------------------------------------------------

    async def ask_category(message: Message, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(NewJobForm.category)
        await message.answer("<b>Новая заявка</b> · шаг 1 из 7\nКакая работа?",
                             reply_markup=kb(*category_rows("nj:cat:"), [CANCEL]))

    async def ask_title(message: Message, state: FSMContext) -> None:
        await state.set_state(NewJobForm.title)
        await message.answer("Шаг 2 из 7 · Что нужно сделать? Коротко, одной строкой.\n"
                             "Например: <i>Разгрузить фуру с мебелью</i>", reply_markup=kb([CANCEL]))

    async def ask_unit(message: Message, state: FSMContext) -> None:
        await state.set_state(NewJobForm.unit)
        units = [btn(label.capitalize(), f"nj:unit:{key}") for key, label in PAY_UNITS.items()]
        await message.answer("Шаг 3 из 7 · Как платите?", reply_markup=kb(units[:2], units[2:], [CANCEL]))

    async def ask_amount(message: Message, state: FSMContext) -> None:
        await state.set_state(NewJobForm.amount)
        unit = PAY_UNITS[(await state.get_data())["pay_unit"]]
        await message.answer(f"Сколько рублей {unit}? Напишите число, например <i>3000</i>.",
                             reply_markup=kb([CANCEL]))

    async def ask_day(message: Message, state: FSMContext) -> None:
        await state.set_state(NewJobForm.day)
        await message.answer("Шаг 4 из 7 · Когда? Выберите день или напишите дату, например <i>15.10</i>.",
                             reply_markup=kb([btn("Сегодня", "nj:day:0"), btn("Завтра", "nj:day:1"),
                                              btn("Послезавтра", "nj:day:2")],
                                             [btn("Без даты, когда удобно", "nj:day:x")], [CANCEL]))

    async def ask_time(message: Message, state: FSMContext) -> None:
        await state.set_state(NewJobForm.time)
        times = [btn(t, f"nj:time:{t}") for t in ("08:00", "09:00", "10:00", "12:00", "14:00", "18:00")]
        await message.answer("Во сколько начало? Выберите или напишите, например <i>9:30</i>.",
                             reply_markup=kb(times[:3], times[3:], [btn("Время договоримся", "nj:time:x")], [CANCEL]))

    async def ask_duration(message: Message, state: FSMContext) -> None:
        await state.set_state(NewJobForm.duration)
        hours = [btn(f"{h} ч", f"nj:dur:{h}") for h in (2, 4, 6, 8, 12)]
        await message.answer("Сколько часов займёт работа? Можно написать число.",
                             reply_markup=kb(hours, [btn("Не знаю", "nj:dur:x")], [CANCEL]))

    async def ask_place(message: Message, state: FSMContext) -> None:
        await state.set_state(NewJobForm.place)
        await state.update_data(metro_id=None, metro_name=None, address=None, lat=None, lng=None)
        await message.answer("Шаг 5 из 7 · Где? Напишите станцию метро (<i>Таганская</i>), адрес "
                             "(<i>Тверская 7</i>) или оба через запятую (<i>Таганская, Марксистская 3</i>). "
                             "Можно отправить геопозицию: 📎 → Геопозиция.", reply_markup=kb([CANCEL]))

    async def ask_workers(message: Message, state: FSMContext) -> None:
        await state.set_state(NewJobForm.workers)
        await message.answer("Шаг 6 из 7 · Сколько человек нужно? Больше пяти — напишите число.",
                             reply_markup=kb([btn(str(n), f"nj:n:{n}") for n in range(1, 6)], [CANCEL]))

    async def ask_description(message: Message, state: FSMContext) -> None:
        await state.set_state(NewJobForm.description)
        await message.answer("Шаг 7 из 7 · Детали: что взять с собой, как найти, когда оплата. "
                             "Напишите одним сообщением или пропустите.",
                             reply_markup=kb([btn("Пропустить", "nj:skip")], [CANCEL]))

    async def ask_confirm(message: Message, state: FSMContext) -> None:
        await state.set_state(NewJobForm.confirm)
        d = await state.get_data()
        await message.answer("<b>Проверьте заявку</b>\n\n" + preview(d),
                             reply_markup=kb([btn("✅ Опубликовать", "nj:pub")],
                                             [btn("✏️ Заполнить заново", "nj:start"), CANCEL]))

    # --- обработчики ------------------------------------------------------------

    @r.message(Command("new"))
    @r.message(F.text == BTN_NEW)
    async def new(message: Message, state: FSMContext) -> None:
        await ask_category(message, state)

    @r.callback_query(F.data == "nj:start")
    async def new_from_button(call: CallbackQuery, state: FSMContext) -> None:
        await call.answer()
        await ask_category(call.message, state)

    @r.callback_query(NewJobForm.category, F.data.startswith("nj:cat:"))
    async def category(call: CallbackQuery, state: FSMContext) -> None:
        cat = call.data[7:]
        if cat not in CATEGORIES:
            await call.answer()
            return
        await state.update_data(category=cat)
        await chosen(call, CATEGORIES[cat][0])
        await ask_title(call.message, state)

    @r.message(NewJobForm.title, ANSWER)
    async def title(message: Message, state: FSMContext) -> None:
        text = rules.clean(message.text) or ""
        if not 3 <= len(text) <= 100:
            await message.answer("Нужно от 3 до 100 знаков. Подробности добавите на последнем шаге.")
            return
        if flags := rules.scam_flags(text):
            await message.answer(f"Такую заявку опубликовать нельзя: {SCAM_FLAGS[flags[0]]}. "
                                 "Если это ошибка, переформулируйте.")
            return
        await state.update_data(title=text)
        await ask_unit(message, state)

    @r.callback_query(NewJobForm.unit, F.data.startswith("nj:unit:"))
    async def unit(call: CallbackQuery, state: FSMContext) -> None:
        key = call.data[8:]
        if key not in PAY_UNITS:
            await call.answer()
            return
        await state.update_data(pay_unit=key)
        await chosen(call, PAY_UNITS[key])
        await ask_amount(call.message, state)

    @r.message(NewJobForm.amount, ANSWER)
    async def amount(message: Message, state: FSMContext) -> None:
        value = parse_amount(message.text)
        if not value:
            await message.answer("Напишите сумму числом, например <i>3000</i>.")
            return
        await state.update_data(pay_amount=value)
        await ask_day(message, state)

    async def set_day(message: Message, state: FSMContext, day: date | None) -> None:
        await state.update_data(starts_on=day.isoformat() if day else None, start_time=None)
        if day:
            await ask_time(message, state)
        else:
            await ask_duration(message, state)

    @r.callback_query(NewJobForm.day, F.data.regexp(r"^nj:day:[012x]$"))
    async def day_button(call: CallbackQuery, state: FSMContext) -> None:
        key = call.data[7:]
        day = None if key == "x" else datetime.now(rules.MSK).date() + timedelta(days=int(key))
        await chosen(call, day.strftime("%d.%m") if day else "без даты")
        await set_day(call.message, state, day)

    @r.message(NewJobForm.day, ANSWER)
    async def day_text(message: Message, state: FSMContext) -> None:
        today = datetime.now(rules.MSK).date()
        day = parse_day(message.text, today)
        if not day or day > today + timedelta(days=actions.MAX_DAYS_AHEAD):
            await message.answer(f"Не понял дату. Напишите день и месяц, например <i>15.10</i>, "
                                 f"не дальше {actions.MAX_DAYS_AHEAD} дней вперёд.")
            return
        await set_day(message, state, day)

    async def set_time(message: Message, state: FSMContext, at: time | None) -> bool:
        d = await state.get_data()
        if at and d.get("starts_on"):
            start = rules.starts_at(date.fromisoformat(d["starts_on"]), at)
            if start < datetime.now(rules.MSK) - timedelta(minutes=30):
                await message.answer("Это время уже прошло. Выберите другое или другой день: /new")
                return False
        await state.update_data(start_time=at.strftime("%H:%M") if at else None)
        await ask_duration(message, state)
        return True

    @r.callback_query(NewJobForm.time, F.data.startswith("nj:time:"))
    async def time_button(call: CallbackQuery, state: FSMContext) -> None:
        key = call.data[8:]
        at = None if key == "x" else parse_time(key)
        await call.answer()
        if await set_time(call.message, state, at):
            await chosen(call, key if at else "договоримся")

    @r.message(NewJobForm.time, ANSWER)
    async def time_text(message: Message, state: FSMContext) -> None:
        at = parse_time(message.text)
        if not at:
            await message.answer("Напишите время как <i>9:30</i> или <i>18</i>.")
            return
        await set_time(message, state, at)

    @r.callback_query(NewJobForm.duration, F.data.regexp(r"^nj:dur:(\d+|x)$"))
    async def duration_button(call: CallbackQuery, state: FSMContext) -> None:
        key = call.data[7:]
        await state.update_data(duration_hours=None if key == "x" else float(key))
        await chosen(call, f"{key} ч" if key != "x" else "не знаю")
        await ask_place(call.message, state)

    @r.message(NewJobForm.duration, ANSWER)
    async def duration_text(message: Message, state: FSMContext) -> None:
        hours = parse_number(message.text)
        if not hours or not 0 < hours <= 24:
            await message.answer("Напишите число часов от 1 до 24.")
            return
        await state.update_data(duration_hours=hours)
        await ask_place(message, state)

    async def find_metro(name: str) -> list:
        key = _METRO_PREFIX.sub("", name).strip().lower().replace("ё", "е")
        if len(key) < 3:
            return []
        return await pool.fetch(
            """SELECT id, name, line FROM metro_stations
               WHERE city = 'moscow' AND replace(lower(name), 'ё', 'е') LIKE $1 || '%'
               ORDER BY replace(lower(name), 'ё', 'е') = $1 DESC, name LIMIT 6""",
            key,
        )

    @r.message(NewJobForm.place, ANSWER)
    async def place_text(message: Message, state: FSMContext) -> None:
        text = rules.clean(message.text) or ""
        if len(text) > 200:
            await message.answer("Слишком длинно: до 200 знаков.")
            return
        head, _, rest = text.partition(",")
        found = await find_metro(head)
        exact = [m for m in found if m["name"].lower().replace("ё", "е") ==
                 _METRO_PREFIX.sub("", head).strip().lower().replace("ё", "е")]
        if exact:
            m = exact[0]
            await state.update_data(metro_id=m["id"], metro_name=m["name"], address=rules.clean(rest))
            await ask_workers(message, state)
        elif found and not rest:
            await state.update_data(address=text)
            rows = [[btn(f"Ⓜ️ {m['name']} ({m['line']})"[:60], f"nj:metro:{m['id']}")] for m in found]
            await message.answer("Какая станция?", reply_markup=kb(*rows, [btn("Это адрес, не метро", "nj:addr")]))
        else:
            await state.update_data(address=text)
            await ask_workers(message, state)

    @r.callback_query(NewJobForm.place, F.data.startswith("nj:metro:"))
    async def place_metro(call: CallbackQuery, state: FSMContext) -> None:
        m = await pool.fetchrow("SELECT id, name FROM metro_stations WHERE id = $1", call.data[9:])
        if not m:
            await call.answer()
            return
        await state.update_data(metro_id=m["id"], metro_name=m["name"], address=None)
        await chosen(call, f"м. {m['name']}")
        await ask_workers(call.message, state)

    @r.callback_query(NewJobForm.place, F.data == "nj:addr")
    async def place_address(call: CallbackQuery, state: FSMContext) -> None:
        await chosen(call, "адрес")
        await ask_workers(call.message, state)

    @r.message(NewJobForm.place, F.location)
    async def place_location(message: Message, state: FSMContext) -> None:
        loc = message.location
        m = await pool.fetchrow(
            """SELECT id, name FROM metro_stations
               WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3)
               ORDER BY location <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography LIMIT 1""",
            loc.longitude, loc.latitude, NEAREST_METRO_M,
        )
        await state.update_data(lat=loc.latitude, lng=loc.longitude,
                                metro_id=m["id"] if m else None, metro_name=m["name"] if m else None)
        await message.answer("📍 Точку запомнил" + (f", рядом м. {m['name']}." if m else "."), reply_markup=MENU)
        await ask_workers(message, state)

    @r.callback_query(NewJobForm.workers, F.data.regexp(r"^nj:n:\d+$"))
    async def workers_button(call: CallbackQuery, state: FSMContext) -> None:
        n = int(call.data[5:])
        await state.update_data(workers_needed=n)
        await chosen(call, str(n))
        await ask_description(call.message, state)

    @r.message(NewJobForm.workers, ANSWER)
    async def workers_text(message: Message, state: FSMContext) -> None:
        n = parse_number(message.text)
        if not n or n != int(n) or not 1 <= n <= 50:
            await message.answer("Напишите число от 1 до 50.")
            return
        await state.update_data(workers_needed=int(n))
        await ask_description(message, state)

    @r.callback_query(NewJobForm.description, F.data == "nj:skip")
    async def description_skip(call: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(description=None)
        await chosen(call, "без деталей")
        await ask_confirm(call.message, state)

    @r.message(NewJobForm.description, ANSWER)
    async def description(message: Message, state: FSMContext) -> None:
        if len(message.text) > 2000:
            await message.answer(f"Длинновато: {len(message.text)} знаков из 2000.")
            return
        await state.update_data(description=message.text)
        await ask_confirm(message, state)

    @r.callback_query(NewJobForm.confirm, F.data == "nj:pub")
    async def publish(call: CallbackQuery, state: FSMContext) -> None:
        d = await state.get_data()
        body = actions.NewJob(
            category=d["category"], title=d["title"], description=d.get("description"),
            workers_needed=d["workers_needed"], pay_amount=d["pay_amount"], pay_unit=d["pay_unit"],
            starts_on=date.fromisoformat(d["starts_on"]) if d.get("starts_on") else None,
            start_time=time.fromisoformat(d["start_time"]) if d.get("start_time") else None,
            duration_hours=d.get("duration_hours"), metro_id=d.get("metro_id"), address=d.get("address"),
            lat=d.get("lat"), lng=d.get("lng"),
        )
        try:
            async with pool.acquire() as conn:
                job_id = await actions.create_job(conn, geocoder, call.from_user.id, body)
        except actions.ActionError as e:
            await call.answer(e.detail, show_alert=True)
            return
        await state.clear()
        await ensure_role(pool, call.from_user.id, "employer")
        await chosen(call, "опубликовано")
        await call.message.answer(
            "✅ Заявка опубликована. Исполнители с подходящей подпиской получат её сразу. "
            "Отклики будут приходить сюда, принять или отклонить можно прямо в чате.",
            reply_markup=kb([btn("⚙️ Управлять заявкой", f"mj:{job_id}")],
                            [app("Открыть в приложении", f"?job={job_id}")]))

    return r
