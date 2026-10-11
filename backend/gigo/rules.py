"""Правила для заявок: признаки мошенничества, ₽/час и срок жизни заявки."""

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

_SCAM_RULES: dict[str, re.Pattern] = {
    "drugs": re.compile(r"закладк|кладмен|\bклад(?:ы|ов)?\b|\bминер(?:ы|а)?\b|тайник|"
                        r"курьер.{0,40}(?:высок\w* доход|от \d{3} ?000|\d{3} ?000 ?(?:р|₽)? ?в (?:неделю|месяц))|"
                        r"\bвес\b.{0,20}\bграмм|\bшоп\b", re.I),
    "bank_card": re.compile(r"\b(?:оформить|открыть|передать|продать|сдать|оформи|открой|передай|продай|сдай)\b"
                            r".{0,20}карт|карт[уы] в аренду|\bдроп(?:ы|ов)?\b|\bобнал", re.I),
    "crypto": re.compile(r"крипт|usdt|биткоин|bitcoin|\bp2p\b|обмен валют|арбитраж", re.I),
    "prepayment": re.compile(r"(?:оплатить|заплатить|взнос|залог)\w*.{0,30}(?:обучени|форм[уы]|оформлени|медкнижк)|предоплат", re.I),
    "adult": re.compile(r"интим|эскорт|18\+|вебкам|webcam", re.I),
}


def scam_flags(text: str) -> list[str]:
    return [name for name, rule in _SCAM_RULES.items() if rule.search(text)]


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


def clean(s: str | None) -> str | None:
    """Без управляющих символов и подмены направления текста; пустая строка → None."""
    return _CONTROL.sub("", s or "").strip() or None


# --- оплата -------------------------------------------------------------

DEFAULT_SHIFT_HOURS = 8


def pay_per_hour(amount: float | None, unit: str | None, duration: float | None) -> tuple[float | None, bool]:
    """(₽/час, посчитано ли с допущением)."""
    if not amount or not unit:
        return None, False
    if unit == "hour":
        return float(amount), False
    if unit in ("shift", "day", "task"):
        if duration and duration > 0:
            return round(amount / duration), False
        if unit == "task":
            return None, False
        return round(amount / DEFAULT_SHIFT_HOURS), True
    return None, False


def pay_total(amount: float | None, unit: str | None, duration: float | None) -> float | None:
    if not amount or not unit:
        return None
    if unit == "hour":
        return round(amount * duration) if duration else None
    if unit in ("shift", "day", "task"):
        return float(amount)
    return None


# --- время --------------------------------------------------------------

UNDATED_TTL = timedelta(days=3)


def starts_at(day: date | None, at: time | None) -> datetime | None:
    if day and at:
        return datetime.combine(day, at, tzinfo=MSK)
    return None


def expires_at(created: datetime, day: date | None, start: datetime | None) -> datetime:
    """Когда заявку убрать из ленты.

    Есть время начала: через час после старта. Есть только день: конец этого дня. Иначе: 3 дня.
    """
    if start:
        return start + timedelta(hours=1)
    if day:
        return datetime.combine(day + timedelta(days=1), time(0), tzinfo=MSK)
    return created + UNDATED_TTL
