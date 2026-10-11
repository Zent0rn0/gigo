"""Сообщения бота о событиях в заявках. API кладёт их в outbox, бот отправляет.

Кнопки: {"text": ..., "path": "?job=42"} открывает Mini App, {"text": ..., "data": "acc:7"} нажимается прямо в чате.
"""

import json

from gigo.categories import REPORT_REASONS
from gigo.format import esc


def contact_url(user_id: int, username: str | None) -> str:
    return f"https://t.me/{username}" if username else f"tg://user?id={user_id}"


def contact_html(user_id: int, name: str | None, username: str | None) -> str:
    label = esc(name or "Профиль")
    link = f'<a href="{contact_url(user_id, username)}">{label}</a>'
    return link + (f" (@{esc(username)})" if username else "")


def job_button(job_id: int, text: str = "Открыть заявку") -> dict:
    return {"text": text, "path": f"?job={job_id}"}


async def push(conn, user_id: int, text: str, *rows: list[dict]) -> None:
    await conn.execute(
        "INSERT INTO outbox (user_id, text, buttons) VALUES ($1, $2, $3::jsonb)",
        user_id, text, json.dumps([r for r in rows if r], ensure_ascii=False) if rows else None,
    )


async def new_response(conn, job, worker, message: str | None, response_id: int) -> None:
    text = f"🙋 Новый отклик на «{esc(job['title'])}»\n<b>{esc(worker['first_name'] or 'Исполнитель')}</b>"
    rating = await conn.fetchrow("SELECT round(avg(rating), 1) AS r, count(*) AS n FROM reviews WHERE target_id = $1",
                                 worker["tg_id"])
    text += f" · ★ {rating['r']} ({rating['n']})" if rating["n"] else " · пока без отзывов"
    if message:
        text += f"\n«{esc(message)}»"
    await push(conn, job["employer_id"], text,
               [{"text": "✅ Принять", "data": f"acc:{response_id}"}, {"text": "✖️ Отклонить", "data": f"rej:{response_id}"}],
               [job_button(job["id"], "Все отклики")])


async def accepted(conn, job, worker, employer) -> None:
    await push(
        conn, worker["tg_id"],
        f"✅ Вас выбрали на «{esc(job['title'])}»\n"
        f"Заказчик: {contact_html(employer['tg_id'], employer['first_name'], employer['username'])}. "
        "Напишите ему, чтобы договориться о деталях.\n\n"
        "Не платите заказчику за «оформление» или форму и не передавайте данные карты.",
        [job_button(job["id"])],
    )
    await push(
        conn, employer["tg_id"],
        f"Вы приняли отклик на «{esc(job['title'])}»\n"
        f"Исполнитель: {contact_html(worker['tg_id'], worker['first_name'], worker['username'])}",
        [job_button(job["id"])],
    )


async def rejected(conn, job, worker_id: int, reason: str = "Заказчик выбрал другого исполнителя") -> None:
    await push(conn, worker_id, f"{reason} на «{esc(job['title'])}». Посмотрите другие заявки.",
               [{"text": "Открыть ленту", "path": "?tab=feed"}])


async def withdrawn(conn, job, worker) -> None:
    await push(conn, job["employer_id"],
               f"↩️ {esc(worker['first_name'] or 'Исполнитель')} отказался от «{esc(job['title'])}».",
               [job_button(job["id"])])


async def cancelled(conn, job, worker_id: int) -> None:
    await push(conn, worker_id, f"❌ Заказчик отменил заявку «{esc(job['title'])}».",
               [{"text": "Открыть ленту", "path": "?tab=feed"}])


async def job_hidden(conn, job) -> None:
    await push(conn, job["employer_id"],
               f"🚫 Заявку «{esc(job['title'])}» скрыл модератор: она нарушает правила Gigo. "
               "Если это ошибка, ответьте на это сообщение.")


async def report_to_admin(conn, admin_id: int, job, reason: str, text: str | None, count: int,
                          auto_hidden: bool) -> None:
    body = (f"⚠️ Жалоба на заявку #{job['id']} «{esc(job['title'])}»\n"
            f"Причина: {REPORT_REASONS.get(reason, reason)}" + (f"\n«{esc(text)}»" if text else "") +
            f"\nЖалоб всего: {count}" + ("\nЗаявка скрыта автоматически." if auto_hidden else "") +
            f"\nАвтор заявки: <code>{job['employer_id']}</code>")
    await push(conn, admin_id, body,
               [{"text": "🚫 Скрыть", "data": f"hide:{job['id']}"}, {"text": "👌 Всё в порядке", "data": f"ok:{job['id']}"}],
               [{"text": "⛔ Заблокировать автора", "data": f"ban:{job['employer_id']}"}],
               [job_button(job["id"])])


async def reminder(conn, user_id: int, job, when: str) -> None:
    await push(conn, user_id, f"⏰ Напоминание: «{esc(job['title'])}» {when}.", [job_button(job["id"])])


async def ask_review(conn, user_id: int, job, other_name: str | None) -> None:
    await push(conn, user_id,
               f"Как прошла работа «{esc(job['title'])}»? Оцените {esc(other_name or 'вторую сторону')}: "
               "отзывы помогают другим выбирать.",
               [job_button(job["id"], "★ Оставить отзыв")])


async def job_edited(conn, job, worker_id: int) -> None:
    await push(conn, worker_id,
               f"✏️ Заказчик изменил заявку «{esc(job['title'])}». Проверьте время, место и оплату.",
               [job_button(job["id"])])
