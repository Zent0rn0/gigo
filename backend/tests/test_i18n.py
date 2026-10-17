"""Языки: словари, выбор языка, ответы API и сообщения бота на языке пользователя."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
import pytest

from gigo import i18n
from gigo.i18n_keys import check
from tests.test_api import BOT_TOKEN


def init_data(user_id: int, language_code: str | None) -> str:
    user = {"id": user_id, "first_name": "Алишер"}
    if language_code:
        user["language_code"] = language_code
    fields = {"auth_date": str(int(time.time())), "user": json.dumps(user, ensure_ascii=False)}
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_catalogs_complete():
    keys, errors = check()
    assert keys and not errors, "\n".join(errors[:20])


def test_normalize_and_pick():
    assert i18n.normalize("uz-Latn") == "uz"
    assert i18n.normalize("EN_us") == "en"
    assert i18n.normalize("de") is None
    assert i18n.pick(None, "fr", "hy") == "hy"
    assert i18n.pick(None) == "ru"


def test_translate_fallback_and_plural():
    with i18n.using("en"):
        assert i18n.tr("Нет такого ключа {x}", x=1) == "Нет такого ключа 1"
        assert i18n.plural(1, "день|дня|дней") != i18n.plural(5, "день|дня|дней")
    with i18n.using("ru"):
        assert [i18n.plural(n, "день|дня|дней") for n in (1, 3, 5, 11, 21)] == ["день", "дня", "дней", "дней", "день"]
    assert i18n.current() == "ru"


def test_every_language_translates_menu():
    from gigo.bot.common import BTN_FIND
    seen = {i18n.translate(BTN_FIND, code) for code in i18n.LANGUAGES}
    assert len(seen) == len(i18n.LANGUAGES), "у каждого языка своя подпись кнопки"


@pytest.fixture
async def api(pool, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("DEV_AUTH", "0")
    monkeypatch.delenv("YANDEX_GEOCODER_KEY", raising=False)
    from gigo.api.app import app, mutations

    mutations.hits.clear()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            yield c


async def test_language_from_telegram_then_profile(api, pool):
    me = (await api.get("/api/me", headers={"Authorization": f"tma {init_data(901, 'uz')}"})).json()
    assert me["lang"] == "uz"
    # язык Telegram не перебивает выбранный в профиле
    h = {"Authorization": f"tma {init_data(901, 'en')}"}
    assert (await api.get("/api/me", headers=h)).json()["lang"] == "uz"
    r = await api.patch("/api/me", json={"lang": "hy"}, headers=h)
    assert r.status_code == 200 and r.json()["lang"] == "hy"
    assert await pool.fetchval("SELECT lang FROM users WHERE tg_id = 901") == "hy"
    assert (await api.patch("/api/me", json={"lang": "de"}, headers=h)).status_code == 422
    # неизвестный язык Telegram — не выбран (интерфейс будет русским)
    me = (await api.get("/api/me", headers={"Authorization": f"tma {init_data(902, 'de')}"})).json()
    assert me["lang"] is None


async def test_errors_and_meta_follow_x_lang(api):
    h = {"Authorization": f"tma {init_data(903, None)}"}
    ru = (await api.get("/api/jobs/999999", headers=h)).json()["detail"]
    en = (await api.get("/api/jobs/999999", headers={**h, "X-Lang": "en"})).json()["detail"]
    assert ru != en and en == i18n.translate(ru, "en")
    labels = {c["id"]: c["label"] for c in (await api.get("/api/meta", headers={**h, "X-Lang": "kk"})).json()["categories"]}
    assert labels["loader"] == i18n.translate("Грузчики", "kk") != "Грузчики"
    no_auth = await api.get("/api/me", headers={"X-Lang": "en"})
    assert no_auth.status_code == 401 and no_auth.json()["detail"] == i18n.translate(
        "Откройте приложение из Telegram", "en")


async def test_bot_message_in_recipient_language(pool):
    from gigo import events
    await pool.execute("INSERT INTO users (tg_id, first_name, lang) VALUES (11, 'A', 'en'), (12, 'B', NULL)")
    job = {"id": 5, "title": "Разгрузка"}
    async with pool.acquire() as conn:
        await events.cancelled(conn, job, 11)
        await events.cancelled(conn, job, 12)
    rows = {r["user_id"]: r["text"] for r in await pool.fetch("SELECT user_id, text FROM outbox")}
    assert "Разгрузка" in rows[11] and "Разгрузка" in rows[12]
    assert rows[11] != rows[12] and "Заявка отменена" in rows[12] and "Заявка отменена" not in rows[11]
    assert i18n.current() == "ru", "язык получателя не протекает в остальной код"
