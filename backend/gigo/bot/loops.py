"""Фоновые задачи бота: очередь событий, подписки, напоминания и просьбы об отзыве."""

import asyncio
import json
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from gigo import config, events
from gigo.format import job_message
from gigo.rules import MSK

log = logging.getLogger("gigo.bot")

MAX_ATTEMPTS = 5
SEND_PAUSE = 0.05      # Telegram разрешает ~30 сообщений в секунду
REMIND_BEFORE_HOURS = 2

MATCHES_SQL = """
SELECT DISTINCT ON (j.id, s.user_id)
       j.id, j.category, j.title, j.pay_per_hour, j.pay_estimated, j.pay_total, j.pay_amount, j.pay_unit,
       j.pay_timing, j.starts_on, j.starts_at, j.duration_hours, j.address,
       m.name AS metro_name, s.user_id, s.id AS subscription_id, s.name AS subscription_name
FROM jobs j
JOIN subscriptions s ON s.enabled
JOIN users u ON u.tg_id = s.user_id AND NOT u.bot_blocked AND u.banned_at IS NULL
LEFT JOIN metro_stations m ON m.id = j.metro_id
LEFT JOIN notifications n ON n.user_id = s.user_id AND n.job_id = j.id
WHERE j.created_at > $1 AND j.status = 'open' AND j.expires_at > now() AND j.hidden_at IS NULL AND n.job_id IS NULL
  AND s.user_id <> j.employer_id
  AND (cardinality(s.categories) = 0 OR j.category = ANY(s.categories))
  AND (s.pay_min IS NULL OR j.pay_per_hour >= s.pay_min)
  AND (cardinality(s.metro_ids) = 0 OR j.metro_id = ANY(s.metro_ids))
  AND (s.location IS NULL OR ST_DWithin(j.location, s.location, coalesce(s.radius_km, 5) * 1000))
  AND (NOT s.today_only OR j.starts_on = (now() AT TIME ZONE 'Europe/Moscow')::date
       OR (j.starts_on IS NULL AND j.created_at > now() - interval '12 hours'))
ORDER BY j.id, s.user_id, s.id
"""


def app_url(settings: config.Settings, path: str = "") -> str | None:
    return settings.webapp_url.rstrip("/") + "/" + path.lstrip("/") if settings.webapp_url else None


def keyboard(settings: config.Settings, rows: list[list[dict]] | None) -> InlineKeyboardMarkup | None:
    """Кнопки из outbox: path открывает Mini App, data нажимается в чате. Без WEBAPP_URL кнопки приложения пропускаем."""
    out = []
    for row in rows or []:
        buttons = []
        for b in row:
            if "data" in b:
                buttons.append(InlineKeyboardButton(text=b["text"], callback_data=b["data"]))
            elif url := app_url(settings, b.get("path", "")):
                buttons.append(InlineKeyboardButton(text=b["text"], web_app=WebAppInfo(url=url)))
        if buttons:
            out.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=out) if out else None


def app_button(settings: config.Settings, text: str, path: str = "") -> InlineKeyboardMarkup | None:
    return keyboard(settings, [[{"text": text, "path": path}]])


async def _send(bot: Bot, pool, user_id: int, text: str, markup) -> bool | None:
    """True: отправлено; False: не отправится никогда; None: повторить позже."""
    try:
        await bot.send_message(user_id, text, reply_markup=markup, disable_web_page_preview=True)
        return True
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        return None
    except TelegramForbiddenError:
        await pool.execute("UPDATE users SET bot_blocked = TRUE WHERE tg_id = $1", user_id)
        return False
    except TelegramBadRequest as e:
        log.warning("сообщение %s не отправилось: %s", user_id, e)
        return False
    finally:
        await asyncio.sleep(SEND_PAUSE)


async def notify_once(bot: Bot, pool, settings: config.Settings, since: datetime) -> int:
    rows = await pool.fetch(MATCHES_SQL, since)
    sent = 0
    for r in rows:
        claimed = await pool.fetchval(
            "INSERT INTO notifications (user_id, job_id, subscription_id) VALUES ($1, $2, $3) "
            "ON CONFLICT DO NOTHING RETURNING 1",
            r["user_id"], r["id"], r["subscription_id"],
        )
        if not claimed:
            continue
        ok = await _send(bot, pool, r["user_id"], job_message(r, r["metro_name"], r["subscription_name"]),
                         keyboard(settings, [[{"text": "🙋 Откликнуться", "data": f"ap:{r['id']}"},
                                              {"text": "📄 Подробнее", "data": f"job:{r['id']}"}],
                                             [{"text": "Открыть в приложении", "path": f"?job={r['id']}"}]]))
        if ok is None:
            await pool.execute("DELETE FROM notifications WHERE user_id = $1 AND job_id = $2", r["user_id"], r["id"])
        sent += bool(ok)
    return sent


async def send_outbox_once(bot: Bot, pool, settings: config.Settings) -> int:
    """Отправляет накопившиеся события. Каждое уходит один раз."""
    rows = await pool.fetch(
        "SELECT o.id, o.user_id, o.text, o.buttons FROM outbox o JOIN users u ON u.tg_id = o.user_id "
        "WHERE o.sent_at IS NULL AND o.attempts < $1 AND NOT u.bot_blocked ORDER BY o.id LIMIT 100",
        MAX_ATTEMPTS,
    )
    sent = 0
    for r in rows:
        claimed = await pool.fetchval(
            "UPDATE outbox SET sent_at = now(), attempts = attempts + 1 WHERE id = $1 AND sent_at IS NULL RETURNING 1",
            r["id"],
        )
        if not claimed:
            continue
        buttons = json.loads(r["buttons"]) if isinstance(r["buttons"], str) else r["buttons"]
        try:
            ok = await _send(bot, pool, r["user_id"], r["text"], keyboard(settings, buttons))
        except Exception:
            ok = None
        if ok is None:
            await pool.execute("UPDATE outbox SET sent_at = NULL WHERE id = $1", r["id"])
        sent += bool(ok)
    return sent


# Принятые отклики, работа по которым скоро начнётся.
REMIND_SQL = """
SELECT r.id, r.worker_id, j.id AS job_id, j.title, j.starts_at
FROM responses r JOIN jobs j ON j.id = r.job_id
WHERE r.status = 'accepted' AND r.reminded_at IS NULL AND j.status <> 'cancelled'
  AND j.starts_at BETWEEN now() + interval '10 minutes' AND now() + make_interval(hours => $1)
"""

# Принятые отклики, работа по которым закончилась: просим обе стороны оценить друг друга.
REVIEW_SQL = """
SELECT r.id, r.worker_id, j.employer_id, j.id AS job_id, j.title,
       w.first_name AS worker_name, e.first_name AS employer_name,
       EXISTS (SELECT 1 FROM reviews v WHERE v.job_id = j.id AND v.author_id = r.worker_id) AS worker_reviewed,
       EXISTS (SELECT 1 FROM reviews v WHERE v.job_id = j.id AND v.author_id = j.employer_id
               AND v.target_id = r.worker_id) AS employer_reviewed
FROM responses r JOIN jobs j ON j.id = r.job_id
JOIN users w ON w.tg_id = r.worker_id JOIN users e ON e.tg_id = j.employer_id
WHERE r.status = 'accepted' AND r.review_asked_at IS NULL AND j.status <> 'cancelled'
  AND coalesce(j.starts_at + make_interval(secs => coalesce(j.duration_hours, 4) * 3600), j.expires_at)
      BETWEEN now() - interval '3 days' AND now()
"""


async def remind_once(pool) -> int:
    """Кладёт в outbox напоминания и просьбы об отзыве. Возвращает, сколько событий создано."""
    n = 0
    async with pool.acquire() as conn, conn.transaction():
        for r in await conn.fetch(REMIND_SQL + " FOR UPDATE OF r SKIP LOCKED", REMIND_BEFORE_HOURS):
            job = {"id": r["job_id"], "title": r["title"]}
            await events.reminder(conn, r["worker_id"], job, f"начинается в {r['starts_at'].astimezone(MSK):%H:%M}")
            await conn.execute("UPDATE responses SET reminded_at = now() WHERE id = $1", r["id"])
            n += 1
        for r in await conn.fetch(REVIEW_SQL + " FOR UPDATE OF r SKIP LOCKED"):
            job = {"id": r["job_id"], "title": r["title"]}
            if not r["worker_reviewed"]:
                await events.ask_review(conn, r["worker_id"], job, r["employer_name"], r["id"])
                n += 1
            if not r["employer_reviewed"]:
                await events.ask_review(conn, r["employer_id"], job, r["worker_name"], r["id"])
                n += 1
            await conn.execute("UPDATE responses SET review_asked_at = now() WHERE id = $1", r["id"])
    return n
