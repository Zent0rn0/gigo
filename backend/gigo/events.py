"""Сообщения бота о событиях в заявках. API кладёт их в outbox, бот отправляет.

Кнопки: {"text": ..., "path": "?job=42"} открывает Mini App, {"text": ..., "data": "acc:7"} нажимается прямо в чате.
Текст и кнопки собираются на языке получателя (users.lang): в outbox лежит уже переведённое сообщение.
"""

import json

from gigo import i18n
from gigo.categories import REPORT_REASONS
from gigo.format import esc
from gigo.i18n import N_, tr


def contact_url(user_id: int, username: str | None) -> str:
    return f"https://t.me/{username}" if username else f"tg://user?id={user_id}"


def contact_html(user_id: int, name: str | None, username: str | None) -> str:
    label = esc(name or tr("Профиль"))
    link = f'<a href="{contact_url(user_id, username)}">{label}</a>'
    return link + (f" (@{esc(username)})" if username else "")


def job_button(job_id: int, text: str | None = None) -> dict:
    """text — уже переведённая подпись; без неё «Открыть заявку» на текущем языке."""
    return {"text": text or tr("Открыть заявку"), "path": f"?job={job_id}"}


def feed_buttons() -> list[dict]:
    return [{"text": tr("🔎 Найти работу"), "data": "feed:*:0"}, {"text": tr("Лента в приложении"), "path": "?tab=feed"}]


def safety() -> str:
    return tr("<blockquote>🛡 Не платите за «оформление», форму или обучение и не передавайте "
              "данные карты и коды из СМС.</blockquote>")


def title_html(job) -> str:
    return f"«<b>{esc(job['title'])}</b>»"


async def lang_of(conn, user_id: int):
    """Контекст с языком получателя: with await lang_of(conn, uid): ..."""
    return i18n.using(await i18n.user_lang(conn, user_id))


async def push(conn, user_id: int, text: str, *rows: list[dict], banner: str | None = None) -> None:
    """banner: картинка над сообщением (gigo/bot/banners/<banner>.png); нет файла — уйдёт текстом."""
    await conn.execute(
        "INSERT INTO outbox (user_id, text, buttons, banner) VALUES ($1, $2, $3::jsonb, $4)",
        user_id, text, json.dumps([r for r in rows if r], ensure_ascii=False) if rows else None, banner,
    )


async def new_response(conn, job, worker, message: str | None, response_id: int) -> None:
    rating = await conn.fetchrow("SELECT round(avg(rating), 1) AS r, count(*) AS n FROM reviews WHERE target_id = $1",
                                 worker["tg_id"])
    with await lang_of(conn, job["employer_id"]):
        text = (tr("🙋 <b>Новый отклик</b> на {title}", title=title_html(job)) + "\n\n"
                f"👤 <b>{esc(worker['first_name'] or tr('Исполнитель'))}</b>")
        text += f" · ★ {rating['r']} ({rating['n']})" if rating["n"] else " · " + tr("пока без отзывов")
        if message:
            text += f"\n<blockquote>«{esc(message)}»</blockquote>"
        await push(conn, job["employer_id"], text,
                   [{"text": tr("✅ Принять"), "data": f"acc:{response_id}", "style": "success"},
                    {"text": tr("✖️ Отклонить"), "data": f"rej:{response_id}", "style": "danger"}],
                   [{"text": tr("👥 Все отклики"), "data": f"rl:{job['id']}"},
                    job_button(job["id"], tr("В приложении"))])


async def accepted(conn, job, worker, employer) -> None:
    with await lang_of(conn, worker["tg_id"]):
        await push(
            conn, worker["tg_id"],
            tr("🎉 <b>Вас выбрали!</b>") + f"\n{title_html(job)}\n\n"
            + tr("👤 Заказчик: {contact}",
                 contact=contact_html(employer['tg_id'], employer['first_name'], employer['username'])) + "\n"
            + tr("Напишите ему, чтобы договориться о деталях.") + "\n\n" + safety(),
            [{"text": tr("📄 Открыть заявку"), "data": f"job:{job['id']}"}, job_button(job["id"], tr("В приложении"))],
            banner="accepted",
        )
    with await lang_of(conn, employer["tg_id"]):
        await push(
            conn, employer["tg_id"],
            tr("🤝 <b>Исполнитель выбран</b>") + f"\n{title_html(job)}\n\n"
            f"👤 {contact_html(worker['tg_id'], worker['first_name'], worker['username'])}\n"
            + tr("Напишите ему, чтобы договориться о деталях."),
            [{"text": tr("⚙️ Управлять заявкой"), "data": f"mj:{job['id']}"},
             job_button(job["id"], tr("В приложении"))],
        )


async def rejected(conn, job, worker_id: int, reason: str = N_("Заказчик выбрал другого исполнителя")) -> None:
    """reason — русский ключ (N_), переводится на язык исполнителя."""
    with await lang_of(conn, worker_id):
        await push(conn, worker_id,
                   tr("😔 {reason} на {title}.\nНе расстраивайтесь: посмотрите другие заявки.",
                      reason=tr(reason), title=title_html(job)),
                   feed_buttons())


async def withdrawn(conn, job, worker) -> None:
    with await lang_of(conn, job["employer_id"]):
        await push(conn, job["employer_id"],
                   tr("↩️ <b>{name}</b> отказался от {title}.",
                      name=esc(worker['first_name'] or tr('Исполнитель')), title=title_html(job)) + "\n"
                   + tr("Откройте набор снова или выберите другого из откликов."),
                   [{"text": tr("⚙️ Управлять заявкой"), "data": f"mj:{job['id']}"},
                    job_button(job["id"], tr("В приложении"))])


async def cancelled(conn, job, worker_id: int) -> None:
    with await lang_of(conn, worker_id):
        await push(conn, worker_id,
                   tr("❌ <b>Заявка отменена</b>") + "\n" + tr("Заказчик отменил {title}.", title=title_html(job)),
                   feed_buttons())


async def job_hidden(conn, job) -> None:
    with await lang_of(conn, job["employer_id"]):
        await push(conn, job["employer_id"],
                   tr("🚫 Заявку «{title}» скрыл модератор: она нарушает правила Gigo. "
                      "Если это ошибка, ответьте на это сообщение.", title=esc(job['title'])))


async def report_to_admin(conn, admin_id: int, job, reason: str, text: str | None, count: int,
                          auto_hidden: bool) -> None:
    with await lang_of(conn, admin_id):
        reason_label = tr(REPORT_REASONS[reason]) if reason in REPORT_REASONS else reason
        body = (tr("⚠️ Жалоба на заявку #{id} «{title}»", id=job['id'], title=esc(job['title'])) + "\n"
                + tr("Причина: {reason}", reason=reason_label) + (f"\n«{esc(text)}»" if text else "") + "\n"
                + tr("Жалоб всего: {n}", n=count)
                + ("\n" + tr("Заявка скрыта автоматически.") if auto_hidden else "") + "\n"
                + tr("Автор заявки: <code>{id}</code>", id=job['employer_id']))
        await push(conn, admin_id, body,
                   [{"text": tr("🚫 Скрыть"), "data": f"hide:{job['id']}"},
                    {"text": tr("👌 Всё в порядке"), "data": f"ok:{job['id']}"}],
                   [{"text": tr("⛔ Заблокировать автора"), "data": f"ban:{job['employer_id']}"}],
                   [job_button(job["id"])])


async def reminder(conn, user_id: int, job, when: str) -> None:
    """when — уже на языке получателя (собирается внутри lang_of того же человека)."""
    with await lang_of(conn, user_id):
        await push(conn, user_id,
                   tr("⏰ <b>Скоро работа</b>") + "\n" + f"{title_html(job)} {when}.\n" + tr("Не опаздывайте 🙌"),
                   [{"text": tr("📄 Открыть заявку"), "data": f"job:{job['id']}"},
                    job_button(job["id"], tr("В приложении"))])


async def ask_review(conn, user_id: int, job, other_name: str | None, response_id: int) -> None:
    with await lang_of(conn, user_id):
        await push(conn, user_id,
                   tr("⭐ <b>Как всё прошло?</b>") + f"\n{title_html(job)}\n\n"
                   + tr("Оцените {name}: отзывы помогают другим выбирать.",
                        name=esc(other_name or tr('вторую сторону'))),
                   [{"text": f"{i}★", "data": f"rv:{response_id}:{i}"} for i in range(1, 6)],
                   [job_button(job["id"], tr("Отзыв в приложении"))], banner="review")


async def job_edited(conn, job, worker_id: int) -> None:
    with await lang_of(conn, worker_id):
        await push(conn, worker_id,
                   tr("✏️ <b>Заказчик изменил заявку «{title}»</b>", title=esc(job['title'])) + "\n"
                   + tr("Проверьте время, место и оплату."),
                   [{"text": tr("📄 Открыть заявку"), "data": f"job:{job['id']}"},
                    job_button(job["id"], tr("В приложении"))])


async def invited(conn, job, employer_name: str | None, worker_id: int) -> None:
    with await lang_of(conn, worker_id):
        await push(conn, worker_id,
                   tr("📩 <b>{name} приглашает вас</b> на {title}.",
                      name=esc(employer_name or tr('Заказчик')), title=title_html(job)) + "\n"
                   + tr("Откройте заявку и откликнитесь, если подходит."),
                   [{"text": tr("📄 Открыть заявку"), "data": f"job:{job['id']}"},
                    job_button(job["id"], tr("В приложении"))])
