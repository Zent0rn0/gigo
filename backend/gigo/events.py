"""Сообщения бота о событиях в заявках. API кладёт их в outbox, бот отправляет."""

from gigo.format import esc


def contact_url(user_id: int, username: str | None) -> str:
    return f"https://t.me/{username}" if username else f"tg://user?id={user_id}"


def contact_html(user_id: int, name: str | None, username: str | None) -> str:
    label = esc(name or "Профиль")
    link = f'<a href="{contact_url(user_id, username)}">{label}</a>'
    return link + (f" (@{esc(username)})" if username else "")


async def push(conn, user_id: int, text: str, button_text: str | None = None, button_path: str | None = None) -> None:
    await conn.execute(
        "INSERT INTO outbox (user_id, text, button_text, button_path) VALUES ($1, $2, $3, $4)",
        user_id, text, button_text, button_path,
    )


async def new_response(conn, job, worker, message: str | None) -> None:
    text = f"🙋 Новый отклик на «{esc(job['title'])}»\n{esc(worker['first_name'] or 'Исполнитель')}"
    if message:
        text += f": {esc(message)}"
    await push(conn, job["employer_id"], text, "Посмотреть отклики", f"?job={job['id']}")


async def accepted(conn, job, worker, employer) -> None:
    await push(
        conn, worker["tg_id"],
        f"✅ Вас выбрали на «{esc(job['title'])}»\n"
        f"Заказчик: {contact_html(employer['tg_id'], employer['first_name'], employer['username'])}. "
        "Напишите ему, чтобы договориться о деталях.",
        "Открыть заявку", f"?job={job['id']}",
    )
    await push(
        conn, employer["tg_id"],
        f"Вы приняли отклик на «{esc(job['title'])}»\n"
        f"Исполнитель: {contact_html(worker['tg_id'], worker['first_name'], worker['username'])}",
        "Открыть заявку", f"?job={job['id']}",
    )


async def rejected(conn, job, worker_id: int, reason: str = "Заказчик выбрал другого исполнителя") -> None:
    await push(conn, worker_id, f"{reason} на «{esc(job['title'])}». Посмотрите другие заявки.",
               "Открыть ленту", "?tab=feed")


async def withdrawn(conn, job, worker) -> None:
    await push(conn, job["employer_id"],
               f"↩️ {esc(worker['first_name'] or 'Исполнитель')} отказался от «{esc(job['title'])}».",
               "Открыть заявку", f"?job={job['id']}")


async def cancelled(conn, job, worker_id: int) -> None:
    await push(conn, worker_id, f"❌ Заказчик отменил заявку «{esc(job['title'])}».", "Открыть ленту", "?tab=feed")
