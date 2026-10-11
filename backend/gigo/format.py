"""Человеческий вид оплаты и времени: для сообщений бота."""

from datetime import date, datetime

from gigo.categories import CATEGORIES
from gigo.parser.rules import MSK

_UNITS = {"hour": "ч", "shift": "смену", "day": "день", "task": "работу", "month": "мес"}


def money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def pay_line(per_hour, estimated, total, amount, unit, timing) -> str | None:
    parts = []
    if per_hour:
        parts.append(("≈" if estimated else "") + money(per_hour) + "/ч")
        if unit and unit != "hour" and amount:
            parts.append(f"{money(amount)} за {_UNITS[unit]}")
        elif total:
            parts.append("≈" + money(total))
    elif amount and unit:
        parts.append(f"{money(amount)} за {_UNITS[unit]}")
    if timing:
        parts.append(timing)
    return " · ".join(parts) or None


def when_line(starts_on: date | None, starts_at: datetime | None, duration, today: date | None = None) -> str | None:
    today = today or datetime.now(MSK).date()
    if not starts_on:
        return f"~{duration:g} ч" if duration else None
    delta = (starts_on - today).days
    day = {0: "сегодня", 1: "завтра", 2: "послезавтра"}.get(delta, starts_on.strftime("%d.%m"))
    text = day + (f" {starts_at.astimezone(MSK):%H:%M}" if starts_at else "")
    return text + (f" · ~{float(duration):g} ч" if duration else "")


def job_message(job, metro_name: str | None, subscription: str | None = None) -> str:
    label, emoji = CATEGORIES.get(job["category"], CATEGORIES["other"])
    lines = []
    if subscription:
        lines.append(f"🔔 По подписке «{subscription}»\n")
    lines.append(f"{emoji} <b>{_esc(job['title'])}</b>")
    pay = pay_line(job["pay_per_hour"], job["pay_estimated"], job["pay_total"], job["pay_amount"],
                   job["pay_unit"], job["pay_timing"])
    if pay:
        lines.append(f"💰 {_esc(pay)}")
    where = f"м. {metro_name}" if metro_name else job["address"]
    if where:
        lines.append(f"📍 {_esc(where)}")
    when = when_line(job["starts_on"], job["starts_at"], job["duration_hours"])
    if when:
        lines.append(f"🕑 {when}")
    return "\n".join(lines)


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
