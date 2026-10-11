"""Правила без ИИ: отсев флуда, признаки мошенничества, телефоны, ₽/час и срок жизни заказа."""

import hashlib
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

# Если в тексте нет ни одного такого слова, это не объявление о работе: ИИ не зовём.
_JOB_HINTS = re.compile(
    r"нуж[не]|требу|ищем|ищу|работ|подработ|ваканс|смен|оплат|зарплат|з/п|зп\b|₽|руб|\d\s*р\b|р/ч|"
    r"грузчик|курьер|разнорабоч|уборк|склад|промоутер|монтаж|сборщ|упаковщ|комплектовщ|официант|повар|"
    r"водител|выход|в\s+час|/час|за\s+час|\d{3,}\s*(?:р|₽)",
    re.I,
)

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

_PHONE = re.compile(r"(?<!\d)(?:\+?7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")


def looks_like_job(text: str) -> bool:
    return bool(_JOB_HINTS.search(text))


def scam_flags(text: str) -> list[str]:
    return [name for name, rule in _SCAM_RULES.items() if rule.search(text)]


def extract_phone(text: str) -> str | None:
    if m := _PHONE.search(text):
        digits = re.sub(r"\D", "", m.group(0))
        return "7" + digits[-10:]
    return None


def normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return "7" + digits[-10:] if len(digits) >= 10 else None


def text_hash(text: str) -> str:
    """Одинаковые репосты дают одинаковый хеш, даже с другими смайликами и пробелами."""
    norm = re.sub(r"[^0-9a-zа-я]+", "", text.lower().replace("ё", "е"))
    return hashlib.sha1(norm.encode()).hexdigest()


# --- оплата -------------------------------------------------------------

DEFAULT_SHIFT_HOURS = 8
MONTH_HOURS = 22 * 8


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
    if unit == "month":
        return round(amount / MONTH_HOURS), True
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

def starts_at(day: date | None, at: time | None) -> datetime | None:
    if day and at:
        return datetime.combine(day, at, tzinfo=MSK)
    return None


def expires_at(sent_at: datetime, day: date | None, start: datetime | None,
               duration: float | None, unit: str | None) -> datetime:
    """Когда заказ убрать из ленты.

    Есть время начала: через час после старта (дальше уже не успеть).
    Есть только день: конец этого дня. Постоянная работа (оклад в месяц): 3 дня.
    Иначе: сутки с публикации.
    """
    if start:
        return start + timedelta(hours=1)
    if day:
        return datetime.combine(day + timedelta(days=1), time(0), tzinfo=MSK)
    if unit == "month":
        return sent_at + timedelta(days=3)
    return sent_at + timedelta(hours=24)
