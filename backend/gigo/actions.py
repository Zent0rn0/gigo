"""Действия с откликами, заявками и жалобами. Общие для API и кнопок бота.

Каждая функция работает в переданной транзакции и бросает ActionError с текстом для человека.
"""

from datetime import datetime, timezone

from gigo import events

REPORTS_TO_HIDE = 3


class ActionError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


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
