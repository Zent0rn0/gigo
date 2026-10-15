"""Языки интерфейса бота и сообщений API.

Ключ перевода — сам русский текст: tr("Лента") вернёт перевод на язык текущего пользователя,
а если перевода нет — русский текст как есть. Переводы лежат в gigo/locales/<язык>.json.
Подстановки — через str.format: tr("Нужно: {n}").format(n=3) или tr("Нужно: {n}", n=3).
Множественное число: plural(n, "день|дня|дней") — в переводе одна, две (one|other) или три формы.

Язык текущего пользователя хранится в contextvar: бот выставляет его в middleware, API — по пользователю
или заголовку X-Lang. Сообщения из outbox собираются с языком получателя (using / user_lang).
"""

import contextvars
import json
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

DEFAULT = "ru"

# Порядок — как в списке выбора. Название — на самом языке.
LANGUAGES: dict[str, str] = {
    "ru": "Русский",
    "en": "English",
    "uz": "Oʻzbekcha",
    "tg": "Тоҷикӣ",
    "ky": "Кыргызча",
    "kk": "Қазақша",
    "az": "Azərbaycanca",
    "hy": "Հայերեն",
}

FLAGS: dict[str, str] = {"ru": "🇷🇺", "en": "🇬🇧", "uz": "🇺🇿", "tg": "🇹🇯", "ky": "🇰🇬", "kk": "🇰🇿",
                         "az": "🇦🇿", "hy": "🇦🇲"}

_DIR = Path(__file__).parent / "locales"
_current: contextvars.ContextVar[str] = contextvars.ContextVar("gigo_lang", default=DEFAULT)


def normalize(code: str | None) -> str | None:
    """Код языка из Telegram или заголовка («uz-Latn», «en-US») → поддерживаемый код или None."""
    if not code or not isinstance(code, str):
        return None
    base = code.strip().lower().replace("_", "-").split("-")[0]
    return base if base in LANGUAGES else None


def pick(*codes: str | None) -> str:
    """Первый поддерживаемый язык из списка, иначе русский."""
    for c in codes:
        n = normalize(c)
        if n:
            return n
    return DEFAULT


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict[str, str]:
    if lang == DEFAULT or lang not in LANGUAGES:
        return {}
    path = _DIR / f"{lang}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, str) and v}


def current() -> str:
    return _current.get()


def set_lang(lang: str | None) -> contextvars.Token:
    return _current.set(normalize(lang) or DEFAULT)


@contextmanager
def using(lang: str | None):
    token = set_lang(lang)
    try:
        yield
    finally:
        _current.reset(token)


def translate(text: str, lang: str | None = None) -> str:
    return catalog(lang or current()).get(text, text)


def tr(text: str, /, **kw) -> str:
    """Перевод на текущий язык; с именованными аргументами сразу подставляет их."""
    out = translate(text)
    if kw:
        try:
            return out.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text.format(**kw)
    return out


def N_(text: str) -> str:
    """Помечает строку для перевода, не переводя её: для констант, которые переводятся при показе через tr()."""
    return text


def _russian_form(n: int) -> int:
    a = abs(n) % 100
    b = a % 10
    if 10 < a < 20:
        return 2
    if 1 < b < 5:
        return 1
    if b == 1:
        return 0
    return 2


def plural(n: int, forms: str, lang: str | None = None) -> str:
    """forms — русские формы через «|»: «день|дня|дней». Возвращает форму на текущем языке."""
    lang = lang or current()
    variants = translate(forms, lang).split("|")
    if len(variants) == 3:
        return variants[_russian_form(n)]
    if len(variants) == 2:
        return variants[0] if abs(n) == 1 else variants[1]
    return variants[0]


def variants(text: str) -> set[str]:
    """Текст на всех языках: чтобы узнать кнопку меню, нажатую на любом из них."""
    return {text, *(catalog(code).get(text, text) for code in LANGUAGES)}


async def user_lang(conn, user_id: int) -> str:
    """Язык пользователя из базы (для сообщений, которые уходят ему из outbox)."""
    lang = await conn.fetchval("SELECT lang FROM users WHERE tg_id = $1", user_id)
    return normalize(lang) or DEFAULT
