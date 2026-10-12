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


FEED_BUTTONS = [{"text": "🔎 Найти работу", "data": "feed:*:0"}, {"text": "Лента в приложении", "path": "?tab=feed"}]


SAFETY = ("<blockquote>🛡 Не платите за «оформление», форму или обучение и не передавайте "
          "данные карты и коды из СМС.</blockquote>")


def title_html(job) -> str:
    return f"«<b>{esc(job['title'])}</b>»"


async def push(conn, user_id: int, text: str, *rows: list[dict], banner: str | None = None) -> None:
    """banner: картинка над сообщением (gigo/bot/banners/<banner>.png); нет файла — уйдёт текстом."""
    await conn.execute(
        "INSERT INTO outbox (user_id, text, buttons, banner) VALUES ($1, $2, $3::jsonb, $4)",
        user_id, text, json.dumps([r for r in rows if r], ensure_ascii=False) if rows else None, banner,
    )


async def new_response(conn, job, worker, message: str | None, response_id: int) -> None:
    text = (f"🙋 <b>Новый отклик</b> на {title_html(job)}\n\n"
            f"👤 <b>{esc(worker['first_name'] or 'Исполнитель')}</b>")
    rating = await conn.fetchrow("SELECT round(avg(rating), 1) AS r, count(*) AS n FROM reviews WHERE target_id = $1",
                                 worker["tg_id"])
    text += f" · ★ {rating['r']} ({rating['n']})" if rating["n"] else " · пока без отзывов"
    if message:
        text += f"\n<blockquote>«{esc(message)}»</blockquote>"
    await push(conn, job["employer_id"], text,
               [{"text": "✅ Принять", "data": f"acc:{response_id}", "style": "success"},
                {"text": "✖️ Отклонить", "data": f"rej:{response_id}", "style": "danger"}],
               [{"text": "👥 Все отклики", "data": f"rl:{job['id']}"}, job_button(job["id"], "В приложении")])


async def accepted(conn, job, worker, employer) -> None:
    await push(
        conn, worker["tg_id"],
        f"🎉 <b>Вас выбрали!</b>\n{title_html(job)}\n\n"
        f"👤 Заказчик: {contact_html(employer['tg_id'], employer['first_name'], employer['username'])}\n"
        "Напишите ему, чтобы договориться о деталях.\n\n" + SAFETY,
        [{"text": "📄 Открыть заявку", "data": f"job:{job['id']}"}, job_button(job["id"], "В приложении")],
        banner="accepted",
    )
    await push(
        conn, employer["tg_id"],
        f"🤝 <b>Исполнитель выбран</b>\n{title_html(job)}\n\n"
        f"👤 {contact_html(worker['tg_id'], worker['first_name'], worker['username'])}\n"
        "Напишите ему, чтобы договориться о деталях.",
        [{"text": "⚙️ Управлять заявкой", "data": f"mj:{job['id']}"}, job_button(job["id"], "В приложении")],
    )


async def rejected(conn, job, worker_id: int, reason: str = "Заказчик выбрал другого исполнителя") -> None:
    await push(conn, worker_id, f"😔 {reason} на {title_html(job)}.\nНе расстраивайтесь: посмотрите другие заявки.",
               FEED_BUTTONS)


async def withdrawn(conn, job, worker) -> None:
    await push(conn, job["employer_id"],
               f"↩️ <b>{esc(worker['first_name'] or 'Исполнитель')}</b> отказался от {title_html(job)}.\n"
               "Откройте набор снова или выберите другого из откликов.",
               [{"text": "⚙️ Управлять заявкой", "data": f"mj:{job['id']}"}, job_button(job["id"], "В приложении")])


async def cancelled(conn, job, worker_id: int) -> None:
    await push(conn, worker_id, f"❌ <b>Заявка отменена</b>\nЗаказчик отменил {title_html(job)}.", FEED_BUTTONS)


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
    await push(conn, user_id, f"⏰ <b>Скоро работа</b>\n{title_html(job)} {when}.\nНе опаздывайте 🙌",
               [{"text": "📄 Открыть заявку", "data": f"job:{job['id']}"}, job_button(job["id"], "В приложении")])


async def ask_review(conn, user_id: int, job, other_name: str | None, response_id: int) -> None:
    await push(conn, user_id,
               f"⭐ <b>Как всё прошло?</b>\n{title_html(job)}\n\n"
               f"Оцените {esc(other_name or 'вторую сторону')}: отзывы помогают другим выбирать.",
               [{"text": f"{i}★", "data": f"rv:{response_id}:{i}"} for i in range(1, 6)],
               [job_button(job["id"], "Отзыв в приложении")], banner="review")


async def job_edited(conn, job, worker_id: int) -> None:
    await push(conn, worker_id,
               f"✏️ <b>Заказчик изменил заявку «{esc(job['title'])}»</b>\nПроверьте время, место и оплату.",
               [{"text": "📄 Открыть заявку", "data": f"job:{job['id']}"}, job_button(job["id"], "В приложении")])


async def invited(conn, job, employer_name: str | None, worker_id: int) -> None:
    await push(conn, worker_id,
               f"📩 <b>{esc(employer_name or 'Заказчик')} приглашает вас</b> на {title_html(job)}.\n"
               "Откройте заявку и откликнитесь, если подходит.",
               [{"text": "📄 Открыть заявку", "data": f"job:{job['id']}"}, job_button(job["id"], "В приложении")])
