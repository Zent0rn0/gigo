import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import pytest

from gigo.api.auth import InitDataError, validate_init_data
from gigo.bot.__main__ import notify_once

BOT_TOKEN = "123456:TEST"


def make_init_data(user_id=777, token=BOT_TOKEN, auth_date=None) -> str:
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAE",
              "user": json.dumps({"id": user_id, "first_name": "Иван", "username": "ivan"}, ensure_ascii=False)}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_init_data_validation():
    user = validate_init_data(make_init_data(), BOT_TOKEN)
    assert user.id == 777 and user.username == "ivan"
    with pytest.raises(InitDataError):
        validate_init_data(make_init_data(token="999:OTHER"), BOT_TOKEN)
    with pytest.raises(InitDataError):
        validate_init_data(make_init_data(auth_date=int(time.time()) - 2 * 86400), BOT_TOKEN)
    with pytest.raises(InitDataError):
        validate_init_data("user=%7B%7D", BOT_TOKEN)


@pytest.fixture
async def client(pool, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("DEV_AUTH", "0")
    from gigo.api.app import app

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                     headers={"Authorization": f"tma {make_init_data()}"}) as c:
            yield c


async def _seed(pool):
    now = datetime.now(timezone.utc)
    await pool.execute(
        "INSERT INTO metro_stations VALUES ('7.1', 'moscow', 'Таганско-Краснопресненская', '943E90', 'Таганская', "
        "ST_SetSRID(ST_MakePoint(37.6533, 55.7393), 4326)::geography), "
        "('2.1', 'moscow', 'Замоскворецкая', '4FB04F', 'Речной вокзал', "
        "ST_SetSRID(ST_MakePoint(37.4762, 55.8547), 4326)::geography)"
    )
    await pool.execute("INSERT INTO sources (link, chat_id, title) VALUES ('@gruz', -1001, 'Грузчики Москва')")
    await pool.execute(
        "INSERT INTO raw_messages (chat_id, message_id, sent_at, text, link) "
        "VALUES (-1001, 5, $1, 'текст', 'https://t.me/gruz/5')", now)

    async def job(title, category, pay, metro, lon, lat, hidden=False, expires=timedelta(hours=5)):
        return await pool.fetchval(
            """INSERT INTO jobs (category, title, pay_per_hour, pay_amount, pay_unit, metro_id, location, hidden,
                                 text_hash, first_seen_at, last_seen_at, expires_at)
               VALUES ($1, $2, $3, $3, 'hour', $4, ST_SetSRID(ST_MakePoint($5, $6), 4326)::geography, $7,
                       'h', $8, $8, $9) RETURNING id""",
            category, title, pay, metro, lon, lat, hidden, now, now + expires)

    a = await job("Грузчики на Таганке", "loader", 500, "7.1", 37.6533, 55.7393)
    b = await job("Курьер на севере", "courier", 350, "2.1", 37.4762, 55.8547)
    await job("Скрытый", "courier", 9000, None, 37.6, 55.7, hidden=True)
    await job("Просроченный", "loader", 600, None, 37.6, 55.7, expires=timedelta(hours=-1))
    await pool.execute("INSERT INTO job_messages SELECT $1, id FROM raw_messages", a)
    return a, b


async def test_auth_required(client):
    resp = await client.get("/api/meta", headers={"Authorization": ""})
    assert resp.status_code == 401
    resp = await client.get("/api/meta", headers={"Authorization": f"tma {make_init_data(token='1:x')}"})
    assert resp.status_code == 401


async def test_jobs_filters(client, pool):
    a, b = await _seed(pool)
    meta = (await client.get("/api/meta")).json()
    assert {c["id"] for c in meta["categories"]} >= {"loader", "courier"}
    assert meta["metro"][0]["color"].startswith("#")

    data = (await client.get("/api/jobs")).json()
    assert data["total"] == 2 and {j["id"] for j in data["items"]} == {a, b}

    data = (await client.get("/api/jobs", params={"category": "loader"})).json()
    job = data["items"][0]
    assert data["total"] == 1 and job["metro"]["name"] == "Таганская" and job["metro"]["color"] == "#943E90"
    assert job["posts"] == [{"link": "https://t.me/gruz/5", "chat": "Грузчики Москва", "sent_at": job["posts"][0]["sent_at"]}]

    assert (await client.get("/api/jobs", params={"pay_min": 400})).json()["total"] == 1
    assert (await client.get("/api/jobs", params=[("metro", "2.1")])).json()["items"][0]["id"] == b

    near = (await client.get("/api/jobs", params={"lat": 55.74, "lng": 37.65, "sort": "distance"})).json()
    assert [j["id"] for j in near["items"]] == [a, b] and near["items"][0]["distance_km"] < 1
    assert (await client.get("/api/jobs", params={"lat": 55.74, "lng": 37.65, "radius_km": 3})).json()["total"] == 1

    assert (await client.get(f"/api/jobs/{a}")).json()["title"] == "Грузчики на Таганке"
    assert (await client.get("/api/jobs/999999")).status_code == 404


async def test_subscriptions_and_notifications(client, pool):
    resp = await client.post("/api/subscriptions", json={"name": "Грузчики от 400", "categories": ["loader"],
                                                         "pay_min": 400})
    assert resp.status_code == 201
    sub = resp.json()
    assert sub["categories"] == ["loader"] and sub["lat"] is None
    near = await client.post("/api/subscriptions", json={"name": "Рядом", "lat": 55.74, "lng": 37.65, "radius_km": 2})
    assert near.json()["lat"] == pytest.approx(55.74)
    assert len((await client.get("/api/subscriptions")).json()) == 2

    a, b = await _seed(pool)  # заказы появились после подписки

    class FakeBot:
        sent = []

        async def send_message(self, chat_id, text, reply_markup=None):
            self.sent.append((chat_id, text))

    from gigo import config
    bot = FakeBot()
    since = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert await notify_once(bot, pool, config.load(), since) == 1  # обе подписки ловят заказ a, но письмо одно
    assert bot.sent[0][0] == 777 and "Грузчики на Таганке" in bot.sent[0][1] and "500 ₽/ч" in bot.sent[0][1]
    assert await notify_once(bot, pool, config.load(), since) == 0  # повторно не шлём

    assert (await client.delete(f"/api/subscriptions/{sub['id']}")).status_code == 204
    assert len((await client.get("/api/subscriptions")).json()) == 1
