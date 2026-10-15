"""Человеческий вид заявок, оплаты и времени: для сообщений бота."""

from datetime import date, datetime

from gigo.categories import CATEGORIES
from gigo.i18n import N_, tr
from gigo.rules import MSK

# Русские ключи: показывать через tr().
_UNITS = {"hour": N_("за ч"), "shift": N_("за смену"), "day": N_("за день"), "task": N_("за работу")}


def money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def pay_line(per_hour, estimated, total, amount, unit, timing) -> str | None:
    parts = []
    if per_hour:
        parts.append(("≈" if estimated else "") + money(per_hour) + tr("/ч"))
        if unit and unit != "hour" and amount:
            parts.append(f"{money(amount)} {tr(_UNITS[unit])}")
        elif total:
            parts.append("≈" + money(total))
    elif amount and unit:
        parts.append(f"{money(amount)} {tr(_UNITS[unit])}")
    if timing:
        parts.append(timing)
    return " · ".join(parts) or None


def when_line(starts_on: date | None, starts_at: datetime | None, duration, today: date | None = None) -> str | None:
    today = today or datetime.now(MSK).date()
    if not starts_on:
        return tr("~{n} ч", n=f"{duration:g}") if duration else None
    delta = (starts_on - today).days
    day = {0: tr("сегодня"), 1: tr("завтра"), 2: tr("послезавтра")}.get(delta, starts_on.strftime("%d.%m"))
    text = day + (f" {starts_at.astimezone(MSK):%H:%M}" if starts_at else "")
    return text + (" · " + tr("~{n} ч", n=f"{float(duration):g}") if duration else "")


def job_message(job, metro_name: str | None, subscription: str | None = None) -> str:
    label, emoji = CATEGORIES.get(job["category"], CATEGORIES["other"])
    lines = []
    if subscription:
        lines.append(tr("🔔 <i>Новая заявка по подписке «{name}»</i>", name=esc(subscription)) + "\n")
    lines.append(f"{emoji} <b>{esc(job['title'])}</b>")
    lines.append(f"<i>{tr(label)}</i>\n")
    pay = pay_line(job["pay_per_hour"], job["pay_estimated"], job["pay_total"], job["pay_amount"],
                   job["pay_unit"], job["pay_timing"])
    if pay:
        lines.append(f"💰 <b>{esc(pay)}</b>")
    where = tr("м. {metro}", metro=metro_name) if metro_name else job["address"]
    if where:
        lines.append(f"📍 {esc(where)}")
    when = when_line(job["starts_on"], job["starts_at"], job["duration_hours"])
    if when:
        lines.append(f"🗓 {when}")
    return "\n".join(lines).rstrip()


def esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
