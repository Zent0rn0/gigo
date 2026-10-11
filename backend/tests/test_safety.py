"""Безопасность, жалобы, модерация и действия бота."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from gigo import actions, config
from gigo.api.limits import RateLimiter
from gigo.bot.loops import keyboard, remind_once, send_outbox_once
from tests.test_api import EMPLOYER, WORKER, FakeBot, _metro, _roles, auth, job_body

ADMIN = 4242


@pytest.fixture
async def client(pool, monkeypatch):
    from tests.test_api import BOT_TOKEN
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("DEV_AUTH", "0")
    monkeypatch.setenv("ADMIN_IDS", str(ADMIN))
    from gigo.api.app import app

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                     headers=auth()) as c:
            yield c


async def _job(client, pool, **kw):
    await _metro(pool)
    await _roles(client)
    return (await client.post("/api/jobs", json=job_body(**kw), headers=auth(EMPLOYER))).json()


def test_rate_limiter():
    rl = RateLimiter(limit=2, window=60)
    assert rl.hit(1, 0) and rl.hit(1, 1) and not rl.hit(1, 2)
    assert rl.hit(2, 2)          # у другого пользователя свой счёт
    assert rl.hit(1, 61)         # окно сдвинулось


async def test_dev_auth_only_local(pool, monkeypatch):
    monkeypatch.setenv("DEV_AUTH", "1")
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    from gigo.api.app import app

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.get("/api/me", headers={"X-Dev-User": "5"})).json()["id"] == 5
            # через туннель или прокси (есть заголовок пересылки) войти без Telegram нельзя
            resp = await c.get("/api/me", headers={"X-Forwarded-For": "1.2.3.4", "X-Dev-User": "5"})
            assert resp.status_code == 401
            resp = await c.get("/api/me", headers={"Cf-Connecting-Ip": "1.2.3.4"})
            assert resp.status_code == 401


async def test_text_cleanup_and_headers(client, pool):
    job = await _job(client, pool, title="Грузчики‮ на склад\x07", description="  ​ ")
    assert job["title"] == "Грузчики на склад" and job["description"] is None
    resp = await client.get("/api/me")
    assert resp.headers["x-content-type-options"] == "nosniff" and resp.headers["cache-control"] == "no-store"


async def test_job_rate_limit(client, pool):
    await _job(client, pool)
    e = auth(EMPLOYER)
    for _ in range(4):
        assert (await client.post("/api/jobs", json=job_body(), headers=e)).status_code == 201
    resp = await client.post("/api/jobs", json=job_body(), headers=e)
    assert resp.status_code == 429 and "5 заявок в час" in resp.json()["detail"]


async def test_reports_hide_and_ban(client, pool):
    job = await _job(client, pool)
    await client.get("/api/me", headers=auth(ADMIN))  # модератор уже знаком боту
    assert (await client.post(f"/api/jobs/{job['id']}/report", json={"reason": "scam"},
                              headers=auth(EMPLOYER))).status_code == 409  # на свою нельзя
    assert (await client.post(f"/api/jobs/{job['id']}/report", json={"reason": "boring"})).status_code == 422
    resp = await client.post(f"/api/jobs/{job['id']}/responses", json={})
    assert resp.status_code == 201

    for uid in (WORKER, 901, 902):
        r = await client.post(f"/api/jobs/{job['id']}/report", json={"reason": "scam", "text": "просят предоплату"},
                              headers=auth(uid))
        assert r.status_code == 204
    # три жалобы: заявка пропала из ленты, автору она видна
    assert (await client.get("/api/jobs")).json()["total"] == 0
    assert (await client.get(f"/api/jobs/{job['id']}", headers=auth(903))).status_code == 404
    assert (await client.get(f"/api/jobs/{job['id']}", headers=auth(EMPLOYER))).status_code == 200

    admin_msgs = await pool.fetch("SELECT text, buttons FROM outbox WHERE user_id = $1 ORDER BY id", ADMIN)
    assert len(admin_msgs) == 3 and "скрыта автоматически" in admin_msgs[-1]["text"]
    buttons = json.loads(admin_msgs[-1]["buttons"])
    assert buttons[0][0]["data"] == f"hide:{job['id']}" and buttons[1][0]["data"] == f"ban:{EMPLOYER}"

    # модератор блокирует автора: заявка отменена, исполнителю сообщили, автор больше не входит
    async with pool.acquire() as conn, conn.transaction():
        assert await actions.ban_user(conn, EMPLOYER) == 1
    resp = await client.get("/api/me", headers=auth(EMPLOYER))
    assert resp.status_code == 403 and "заблокирован" in resp.json()["detail"]
    assert (await client.get(f"/api/jobs/{job['id']}")).json()["status"] == "cancelled"
    texts = [r["text"] for r in await pool.fetch("SELECT text FROM outbox WHERE user_id = $1", WORKER)]
    assert any("отменил" in t for t in texts)

    async with pool.acquire() as conn:
        await actions.unban_user(conn, EMPLOYER)
    assert (await client.get("/api/me", headers=auth(EMPLOYER))).status_code == 200


async def test_accept_from_bot_buttons(client, pool):
    job = await _job(client, pool)
    resp = (await client.post(f"/api/jobs/{job['id']}/responses", json={"message": "Готов"})).json()
    row = await pool.fetchrow("SELECT text, buttons FROM outbox WHERE user_id = $1", EMPLOYER)
    buttons = json.loads(row["buttons"])
    assert buttons[0] == [{"text": "✅ Принять", "data": f"acc:{resp['id']}"},
                          {"text": "✖️ Отклонить", "data": f"rej:{resp['id']}"}]
    assert "пока без отзывов" in row["text"] and "«Готов»" in row["text"]

    settings = config.load()
    kb = keyboard(settings, buttons)
    assert [b.callback_data for b in kb.inline_keyboard[0]] == [f"acc:{resp['id']}", f"rej:{resp['id']}"]
    assert len(kb.inline_keyboard) == 1  # без WEBAPP_URL кнопка приложения пропускается

    # кнопку нажал не заказчик
    async with pool.acquire() as conn:
        with pytest.raises(actions.ActionError):
            await actions.set_response_status(conn, resp["id"], WORKER, "accepted")
    async with pool.acquire() as conn, conn.transaction():
        await actions.set_response_status(conn, resp["id"], EMPLOYER, "accepted")
    assert (await client.get("/api/my/responses")).json()["items"][0]["status"] == "accepted"

    bot = FakeBot()
    assert await send_outbox_once(bot, pool, settings) == 3


async def test_reminder_and_review_requests(client, pool):
    job = await _job(client, pool)
    resp = (await client.post(f"/api/jobs/{job['id']}/responses", json={})).json()
    await client.patch(f"/api/responses/{resp['id']}", json={"status": "accepted"}, headers=auth(EMPLOYER))
    await pool.execute("DELETE FROM outbox")

    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    await pool.execute("UPDATE jobs SET starts_at = $2, duration_hours = 4 WHERE id = $1", job["id"], soon)
    assert await remind_once(pool) == 1
    assert await remind_once(pool) == 0
    assert "Напоминание" in await pool.fetchval("SELECT text FROM outbox WHERE user_id = $1", WORKER)

    # работа закончилась: обе стороны просим оценить, кто уже оценил — не просим
    await client.post("/api/reviews", json={"response_id": resp["id"], "rating": 5})
    await pool.execute("UPDATE jobs SET starts_at = now() - interval '6 hours' WHERE id = $1", job["id"])
    assert await remind_once(pool) == 1
    assert await remind_once(pool) == 0
    assert "Оцените" in (await pool.fetch("SELECT text FROM outbox WHERE user_id = $1", EMPLOYER))[-1]["text"]


class _FakeCall:
    def __init__(self, data, user_id):
        from types import SimpleNamespace
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers, self.edits = [], []
        outer = self

        class Msg:
            html_text = "🙋 Новый отклик"
            reply_markup = None

            async def edit_text(self, text, reply_markup=None):
                outer.edits.append(text)

        self.message = Msg()

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))


async def test_bot_callbacks(client, pool):
    from gigo.bot.handlers import make_dispatcher

    job = await _job(client, pool)
    resp = (await client.post(f"/api/jobs/{job['id']}/responses", json={})).json()
    dp = make_dispatcher(config.load(), pool)
    decide, moderate = (h.callback for h in dp.callback_query.handlers)

    call = _FakeCall(f"acc:{resp['id']}", WORKER)          # не заказчик
    await decide(call)
    assert call.answers == [("Решение по отклику принимает заказчик", True)] and not call.edits

    call = _FakeCall(f"acc:{resp['id']}", EMPLOYER)
    await decide(call)
    assert "Принят" in call.edits[0] and (await client.get("/api/my/responses")).json()["items"][0]["status"] == \
        "accepted"

    call = _FakeCall(f"hide:{job['id']}", EMPLOYER)        # не модератор
    await moderate(call)
    assert call.answers[0][1] is True
    call = _FakeCall(f"hide:{job['id']}", ADMIN)
    await moderate(call)
    assert "скрыта" in call.edits[0]
    assert await pool.fetchval("SELECT hidden_at IS NOT NULL FROM jobs WHERE id = $1", job["id"])
