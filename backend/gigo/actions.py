"""Действия с откликами, заявками и жалобами. Общие для API и кнопок бота.

Каждая функция работает в переданной транзакции и бросает ActionError с текстом для человека.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from gigo import events, rules
from gigo.categories import CATEGORIES, PAY_UNITS, SCAM_FLAGS

REPORTS_TO_HIDE = 3
MAX_OPEN_JOBS = 20
MAX_DAYS_AHEAD = 60


class ActionError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def check_recent(conn, sql: str, user_id: int, limit: int, message: str) -> None:
    """Лимит по базе (переживает перезапуск): sql считает действия пользователя $1 за период."""
    if await conn.fetchval(sql, user_id) >= limit:
        raise ActionError(429, message)


async def _users(conn, *ids: int) -> dict:
    rows = await conn.fetch("SELECT tg_id, first_name, username FROM users WHERE tg_id = ANY($1::bigint[])", list(ids))
    return {u["tg_id"]: u for u in rows}


async def set_response_status(conn, response_id: int, actor_id: int, status: str) -> None:
    """Принять / отклонить (заказчик) или отозвать (исполнитель) отклик."""
    r = await conn.fetchrow("SELECT * FROM responses WHERE id = $1 FOR UPDATE", response_id)
    job = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", r["job_id"]) if r else None
    if not r or actor_id not in (r["worker_id"], job["employer_id"]):
        raise ActionError(404, "Отклик не найден")
    if status == r["status"]:
        return
    if status == "withdrawn":
        if actor_id != r["worker_id"] or r["status"] not in ("pending", "accepted"):
            raise ActionError(409, "Этот отклик нельзя отозвать")
        if r["status"] == "accepted":
            await events.withdrawn(conn, job, (await _users(conn, actor_id))[actor_id])
    elif status in ("accepted", "rejected"):
        if actor_id != job["employer_id"]:
            raise ActionError(403, "Решение по отклику принимает заказчик")
        if r["status"] == "withdrawn":
            raise ActionError(409, "Исполнитель отозвал отклик")
        if status == "accepted" and job["status"] != "open":
            raise ActionError(409, "Заявка закрыта. Откройте её снова, чтобы принять отклик.")
        users = await _users(conn, r["worker_id"], job["employer_id"])
        if status == "accepted":
            await events.accepted(conn, job, users[r["worker_id"]], users[job["employer_id"]])
        else:
            await events.rejected(conn, job, r["worker_id"])
    else:
        raise ActionError(422, "Неизвестный статус")
    await conn.execute("UPDATE responses SET status = $2, updated_at = now() WHERE id = $1", response_id, status)


# --- заявки и отклики: создание ---------------------------------------------------

@dataclass
class NewJob:
    """Заявка от заказчика: из Mini App или из диалога с ботом. Тексты ещё не очищены."""
    category: str
    title: str
    pay_amount: float
    pay_unit: str
    description: str | None = None
    workers_needed: int = 1
    pay_timing: str | None = None
    starts_on: date | None = None
    start_time: time | None = None
    duration_hours: float | None = None
    metro_id: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None


# Колонки заявки из job_fields; lat/lng собираются в location.
JOB_COLUMNS = ("category", "title", "description", "workers_needed", "pay_amount", "pay_unit", "pay_per_hour",
               "pay_estimated", "pay_total", "pay_timing", "starts_on", "starts_at", "duration_hours", "metro_id",
               "address", "expires_at")
LOCATION_SQL = ("CASE WHEN ${lat}::float8 IS NULL THEN NULL "
                "ELSE ST_SetSRID(ST_MakePoint(${lng}, ${lat}), 4326)::geography END")


async def job_fields(conn, geocoder, body: NewJob, created: datetime | None = None) -> dict:
    """Проверенные поля заявки для INSERT/UPDATE. created: когда создана (для срока жизни при правке)."""
    if body.category not in CATEGORIES:
        raise ActionError(422, "Неизвестная категория")
    if body.pay_unit not in PAY_UNITS:
        raise ActionError(422, "Неизвестная единица оплаты")
    title, description, address = rules.clean(body.title), rules.clean(body.description), rules.clean(body.address)
    if not title:
        raise ActionError(422, "Напишите, что нужно сделать")
    if flags := rules.scam_flags(f"{title}\n{description or ''}"):
        raise ActionError(422, f"Заявку нельзя опубликовать: {SCAM_FLAGS[flags[0]]}. "
                               "Если это ошибка, переформулируйте текст.")
    has_point = body.lat is not None and body.lng is not None
    if not (body.metro_id or address or has_point):
        raise ActionError(422, "Укажите метро или адрес")

    now = datetime.now(rules.MSK)
    day, at = body.starts_on, body.start_time
    if at and not day:
        day = now.date()
    if day and not (now.date() <= day <= now.date() + timedelta(days=MAX_DAYS_AHEAD)):
        raise ActionError(422, f"Дата должна быть от сегодня до {MAX_DAYS_AHEAD} дней вперёд")
    start = rules.starts_at(day, at)
    if start and start < now - timedelta(minutes=30):
        raise ActionError(422, "Время начала уже прошло")

    metro = None
    if body.metro_id:
        metro = await conn.fetchrow("SELECT ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
                                    "FROM metro_stations WHERE id = $1", body.metro_id)
        if not metro:
            raise ActionError(422, "Неизвестная станция метро")
    point = (body.lat, body.lng) if has_point else None
    if not point and address and geocoder:
        point = await geocoder.locate(address)
    if not point and metro:
        point = (metro["lat"], metro["lng"])

    per_hour, estimated = rules.pay_per_hour(body.pay_amount, body.pay_unit, body.duration_hours)
    return {
        "category": body.category, "title": title, "description": description,
        "workers_needed": body.workers_needed, "pay_amount": body.pay_amount, "pay_unit": body.pay_unit,
        "pay_per_hour": per_hour, "pay_estimated": estimated,
        "pay_total": rules.pay_total(body.pay_amount, body.pay_unit, body.duration_hours),
        "pay_timing": rules.clean(body.pay_timing), "starts_on": day, "starts_at": start,
        "duration_hours": body.duration_hours, "metro_id": body.metro_id, "address": address,
        "lat": point[0] if point else None, "lng": point[1] if point else None,
        "expires_at": rules.expires_at(created or now, day, start),
    }


async def create_job(conn, geocoder, employer_id: int, body: NewJob) -> int:
    """Проверяет лимиты и поля и сохраняет заявку. Возвращает её id."""
    if await conn.fetchval("SELECT count(*) FROM jobs WHERE employer_id = $1 AND status = 'open' "
                           "AND expires_at > now()", employer_id) >= MAX_OPEN_JOBS:
        raise ActionError(409, f"Открыто уже {MAX_OPEN_JOBS} заявок. Закройте ненужные, чтобы создать новую.")
    await check_recent(conn, "SELECT count(*) FROM jobs WHERE employer_id = $1 "
                             "AND created_at > now() - interval '1 hour'",
                       employer_id, 5, "Не больше 5 заявок в час. Попробуйте позже.")
    fields = await job_fields(conn, geocoder, body)
    n = len(JOB_COLUMNS)
    location = LOCATION_SQL.format(lat=n + 2, lng=n + 3)
    return await conn.fetchval(
        f"""INSERT INTO jobs (employer_id, {", ".join(JOB_COLUMNS)}, location)
            VALUES ($1, {", ".join(f"${i}" for i in range(2, n + 2))}, {location}) RETURNING id""",
        employer_id, *(fields[c] for c in JOB_COLUMNS), fields["lat"], fields["lng"],
    )


async def repeat_job(conn, job_id: int, employer_id: int, day: date) -> int:
    """Новая заявка по образцу старой: те же условия, другой день."""
    job = await conn.fetchrow("SELECT *, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
                              "FROM jobs WHERE id = $1", job_id)
    if not job or job["employer_id"] != employer_id:
        raise ActionError(404, "Заявка не найдена")
    if job["hidden_at"]:
        raise ActionError(409, "Заявку скрыл модератор, повторить её нельзя.")
    at = job["starts_at"].astimezone(rules.MSK).time() if job["starts_at"] else None
    return await create_job(conn, None, employer_id, NewJob(
        category=job["category"], title=job["title"], description=job["description"],
        workers_needed=job["workers_needed"], pay_amount=float(job["pay_amount"]), pay_unit=job["pay_unit"],
        pay_timing=job["pay_timing"], starts_on=day, start_time=at,
        duration_hours=float(job["duration_hours"]) if job["duration_hours"] else None,
        metro_id=job["metro_id"], address=job["address"], lat=job["lat"], lng=job["lng"],
    ))


async def respond(conn, job_id: int, worker_id: int, message: str | None) -> int:
    """Отклик исполнителя на заявку. Возвращает id отклика."""
    message = rules.clean(message)
    job = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
    if not job:
        raise ActionError(404, "Заявка не найдена")
    if job["employer_id"] == worker_id:
        raise ActionError(409, "Это ваша заявка")
    if job["status"] != "open" or job["expires_at"] <= datetime.now(timezone.utc) or job["hidden_at"]:
        raise ActionError(409, "Набор на эту заявку закрыт")
    await check_recent(conn, "SELECT count(*) FROM responses WHERE worker_id = $1 "
                             "AND updated_at > now() - interval '1 hour'",
                       worker_id, 30, "Слишком много откликов за час. Попробуйте позже.")
    resp_id = await conn.fetchval(
        """INSERT INTO responses (job_id, worker_id, message) VALUES ($1, $2, $3)
           ON CONFLICT (job_id, worker_id) DO UPDATE
               SET status = 'pending', message = EXCLUDED.message, updated_at = now()
               WHERE responses.status = 'withdrawn'
           RETURNING id""",
        job_id, worker_id, message,
    )
    if not resp_id:
        raise ActionError(409, "Вы уже откликнулись")
    worker = await conn.fetchrow("SELECT tg_id, first_name, username FROM users WHERE tg_id = $1", worker_id)
    await events.new_response(conn, job, worker, message, resp_id)
    return resp_id


async def save_review(conn, response_id: int, author_id: int, rating: int, text: str | None,
                      keep_text: bool = False) -> str | None:
    """Отзыв второй стороне по принятому отклику. Возвращает очищенный текст.

    keep_text: оценка без текста не стирает уже написанный текст (бот сначала ставит звёзды, потом просит пару слов).
    """
    r = await conn.fetchrow(
        "SELECT r.job_id, r.worker_id, r.status, j.employer_id FROM responses r JOIN jobs j ON j.id = r.job_id "
        "WHERE r.id = $1", response_id)
    if not r or author_id not in (r["worker_id"], r["employer_id"]):
        raise ActionError(404, "Отклик не найден")
    if r["status"] != "accepted":
        raise ActionError(409, "Отзыв можно оставить только после того, как отклик принят")
    if not 1 <= rating <= 5:
        raise ActionError(422, "Оценка от 1 до 5")
    target = r["worker_id"] if author_id == r["employer_id"] else r["employer_id"]
    text = rules.clean(text)
    await conn.execute(
        """INSERT INTO reviews (job_id, author_id, target_id, rating, text) VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (job_id, author_id, target_id) DO UPDATE
               SET rating = EXCLUDED.rating, created_at = now(),
                   text = CASE WHEN $6 THEN coalesce(EXCLUDED.text, reviews.text) ELSE EXCLUDED.text END""",
        r["job_id"], author_id, target, rating, text, keep_text,
    )
    return text


async def set_job_status(conn, job_id: int, actor_id: int, status: str) -> None:
    job = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1 FOR UPDATE", job_id)
    if not job or job["employer_id"] != actor_id:
        raise ActionError(404, "Заявка не найдена")
    if status == job["status"]:
        return
    if status == "open":
        if job["expires_at"] <= datetime.now(timezone.utc):
            raise ActionError(409, "Срок заявки прошёл. Создайте новую.")
        if job["hidden_at"]:
            raise ActionError(409, "Заявку скрыл модератор, открыть её снова нельзя.")
    await conn.execute("UPDATE jobs SET status = $2, updated_at = now() WHERE id = $1", job_id, status)
    if status in ("closed", "cancelled"):
        await close_pending(conn, job, cancelled=status == "cancelled")


async def close_pending(conn, job, cancelled: bool, reason: str = "Набор закрыт") -> None:
    """Ожидающим отклонение; при отмене ещё и принятым сообщаем, что работы не будет."""
    pending = await conn.fetch(
        "UPDATE responses SET status = 'rejected', updated_at = now() "
        "WHERE job_id = $1 AND status = 'pending' RETURNING worker_id", job["id"])
    for r in pending:
        if cancelled:
            await events.cancelled(conn, job, r["worker_id"])
        else:
            await events.rejected(conn, job, r["worker_id"], reason)
    if cancelled:
        for r in await conn.fetch("SELECT worker_id FROM responses WHERE job_id = $1 AND status = 'accepted'",
                                  job["id"]):
            await events.cancelled(conn, job, r["worker_id"])


async def report_job(conn, job_id: int, author_id: int, reason: str, text: str | None,
                     admin_ids: tuple[int, ...]) -> None:
    job = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
    if not job:
        raise ActionError(404, "Заявка не найдена")
    if job["employer_id"] == author_id:
        raise ActionError(409, "Это ваша заявка")
    await conn.execute(
        """INSERT INTO reports (job_id, author_id, reason, text) VALUES ($1, $2, $3, $4)
           ON CONFLICT (job_id, author_id) DO UPDATE
               SET reason = EXCLUDED.reason, text = EXCLUDED.text, created_at = now(), resolved_at = NULL""",
        job_id, author_id, reason, text,
    )
    count = await conn.fetchval("SELECT count(*) FROM reports WHERE job_id = $1 AND resolved_at IS NULL", job_id)
    auto_hidden = False
    if count >= REPORTS_TO_HIDE and not job["hidden_at"]:
        await conn.execute("UPDATE jobs SET hidden_at = now(), hidden_reason = 'жалобы' WHERE id = $1", job_id)
        auto_hidden = True
    # Писать можно только тем модераторам, кто уже запускал бота.
    for row in await conn.fetch("SELECT tg_id FROM users WHERE tg_id = ANY($1::bigint[])", list(admin_ids)):
        admin = row["tg_id"]
        await events.report_to_admin(conn, admin, job, reason, text, count, auto_hidden)


# --- модерация -------------------------------------------------------------

async def hide_job(conn, job_id: int, reason: str = "модератор") -> None:
    job = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1 FOR UPDATE", job_id)
    if not job:
        raise ActionError(404, "Заявка не найдена")
    await conn.execute("UPDATE jobs SET hidden_at = coalesce(hidden_at, now()), hidden_reason = $2, "
                       "status = CASE WHEN status = 'open' THEN 'cancelled' ELSE status END WHERE id = $1",
                       job_id, reason)
    await conn.execute("UPDATE reports SET resolved_at = now() WHERE job_id = $1 AND resolved_at IS NULL", job_id)
    if job["status"] == "open":
        await close_pending(conn, job, cancelled=True)
    await events.job_hidden(conn, job)


async def dismiss_reports(conn, job_id: int) -> None:
    await conn.execute("UPDATE reports SET resolved_at = now() WHERE job_id = $1 AND resolved_at IS NULL", job_id)
    await conn.execute("UPDATE jobs SET hidden_at = NULL, hidden_reason = NULL "
                       "WHERE id = $1 AND hidden_reason = 'жалобы'", job_id)


async def ban_user(conn, user_id: int, reason: str = "нарушение правил") -> int:
    """Блокирует и скрывает все открытые заявки. Возвращает, сколько заявок скрыто."""
    if not await conn.fetchval("UPDATE users SET banned_at = now(), ban_reason = $2 WHERE tg_id = $1 RETURNING 1",
                               user_id, reason):
        raise ActionError(404, "Пользователь не найден")
    jobs = await conn.fetch("SELECT id FROM jobs WHERE employer_id = $1 AND status = 'open'", user_id)
    for j in jobs:
        await hide_job(conn, j["id"], "автор заблокирован")
    await conn.execute("UPDATE responses SET status = 'withdrawn', updated_at = now() "
                       "WHERE worker_id = $1 AND status = 'pending'", user_id)
    return len(jobs)


async def unban_user(conn, user_id: int) -> None:
    await conn.execute("UPDATE users SET banned_at = NULL, ban_reason = NULL WHERE tg_id = $1", user_id)
