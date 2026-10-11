import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import pytest

from gigo.api.auth import InitDataError, validate_init_data
from gigo.bot.__main__ import notify_once, send_outbox_once

BOT_TOKEN = "123456:TEST"


def make_init_data(user_id=777, token=BOT_TOKEN, auth_date=None, name="Иван", username="ivan") -> str:
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAE",
              "user": json.dumps({"id": user_id, "first_name": name, "username": username}, ensure_ascii=False)}
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


WORKER, EMPLOYER = 777, 555


def auth(user_id=WORKER):
    names = {WORKER: ("Иван", "ivan"), EMPLOYER: ("Ольга", None)}
    name, username = names.get(user_id, ("Кто-то", None))
    return {"Authorization": f"tma {make_init_data(user_id, name=name, username=username)}"}


@pytest.fixture
async def client(pool, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("DEV_AUTH", "0")
    monkeypatch.delenv("YANDEX_GEOCODER_KEY", raising=False)
    from gigo.api.app import app

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=auth()) as c:
            yield c


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text))


async def _metro(pool):
    await pool.execute(
        "INSERT INTO metro_stations VALUES ('7.1', 'moscow', 'Таганско-Краснопресненская', '943E90', 'Таганская', "
        "ST_SetSRID(ST_MakePoint(37.6533, 55.7393), 4326)::geography), "
        "('2.1', 'moscow', 'Замоскворецкая', '4FB04F', 'Речной вокзал', "
        "ST_SetSRID(ST_MakePoint(37.4762, 55.8547), 4326)::geography)"
    )


async def _roles(client):
    assert (await client.patch("/api/me", json={"role": "worker"})).json()["role"] == "worker"
    assert (await client.patch("/api/me", json={"role": "employer"}, headers=auth(EMPLOYER))).status_code == 200


def job_body(**kw):
    return {"category": "loader", "title": "Грузчики на Таганке", "pay_amount": 500, "pay_unit": "hour",
            "duration_hours": 4, "metro_id": "7.1", "workers_needed": 2, **kw}


async def test_auth_required(client):
    resp = await client.get("/api/meta", headers={"Authorization": ""})
    assert resp.status_code == 401
    resp = await client.get("/api/meta", headers={"Authorization": f"tma {make_init_data(token='1:x')}"})
    assert resp.status_code == 401


async def test_onboarding_and_roles(client):
    me = (await client.get("/api/me")).json()
    assert me == {"id": WORKER, "username": "ivan", "first_name": "Иван", "role": None, "about": None,
                  "rating": None, "reviews_count": 0}
    assert (await client.patch("/api/me", json={"role": "boss"})).status_code == 422
    me = (await client.patch("/api/me", json={"role": "worker", "about": "  Опыт на складе  "})).json()
    assert me["role"] == "worker" and me["about"] == "Опыт на складе"
    # исполнитель не может создать заявку, заказчик не может откликнуться
    assert (await client.post("/api/jobs", json=job_body())).status_code == 403
    meta = (await client.get("/api/meta")).json()
    assert [u["id"] for u in meta["pay_units"]] == ["hour", "shift", "day", "task"]


async def test_create_job_validation(client, pool):
    await _metro(pool)
    await _roles(client)
    e = auth(EMPLOYER)
    resp = await client.post("/api/jobs", json=job_body(start_time="23:59", title="Нужны кладмены"), headers=e)
    assert resp.status_code == 422 and "закладчиков" in resp.json()["detail"]
    resp = await client.post("/api/jobs", json=job_body(metro_id=None), headers=e)
    assert resp.status_code == 422 and resp.json()["detail"] == "Укажите метро или адрес"
    assert (await client.post("/api/jobs", json=job_body(metro_id="99.9"), headers=e)).status_code == 422
    assert (await client.post("/api/jobs", json=job_body(starts_on="2020-01-01"), headers=e)).status_code == 422

    job = (await client.post("/api/jobs", json=job_body(pay_amount=3200, pay_unit="shift", duration_hours=None),
                             headers=e)).json()
    assert job["status"] == "open" and job["is_mine"] and job["pending_count"] == 0 and job["responses"] == []
    assert job["pay_per_hour"] == 400 and job["pay_estimated"] and job["pay_total"] == 3200
    assert job["metro"]["name"] == "Таганская" and job["lat"] == pytest.approx(55.7393)
    assert job["employer"] == {"id": EMPLOYER, "first_name": "Ольга", "rating": None, "reviews_count": 0}

    job = (await client.post("/api/jobs", json=job_body(metro_id=None, address="ул. Ленина, 1", lat=55.8, lng=37.5),
                             headers=e)).json()
    assert job["address"] == "ул. Ленина, 1" and job["lat"] == pytest.approx(55.8) and job["metro"] is None


async def test_feed_filters(client, pool):
    await _metro(pool)
    await _roles(client)
    e = auth(EMPLOYER)
    a = (await client.post("/api/jobs", json=job_body(), headers=e)).json()["id"]
    b = (await client.post("/api/jobs", json=job_body(category="courier", title="Курьер на севере", pay_amount=350,
                                                      metro_id="2.1"), headers=e)).json()["id"]
    c = (await client.post("/api/jobs", json=job_body(title="Отменённая"), headers=e)).json()["id"]
    await client.patch(f"/api/jobs/{c}", json={"status": "cancelled"}, headers=e)

    data = (await client.get("/api/jobs")).json()
    assert data["total"] == 2 and [j["id"] for j in data["items"]] == [b, a]
    item = data["items"][1]
    assert item["is_mine"] is False and item["my_response"] is None and "pending_count" not in item

    assert (await client.get("/api/jobs", params={"category": "loader"})).json()["total"] == 1
    assert (await client.get("/api/jobs", params={"pay_min": 400})).json()["total"] == 1
    assert (await client.get("/api/jobs", params=[("metro", "2.1")])).json()["items"][0]["id"] == b
    near = (await client.get("/api/jobs", params={"lat": 55.74, "lng": 37.65, "sort": "distance"})).json()
    assert [j["id"] for j in near["items"]] == [a, b] and near["items"][0]["distance_km"] < 1
    assert (await client.get("/api/jobs", params={"lat": 55.74, "lng": 37.65, "radius_km": 3})).json()["total"] == 1

    await pool.execute("UPDATE jobs SET expires_at = now() - interval '1 hour' WHERE id = $1", b)
    assert (await client.get("/api/jobs")).json()["total"] == 1
    assert (await client.get(f"/api/jobs/{b}")).status_code == 404  # чужая просроченная
    assert (await client.get(f"/api/jobs/{b}", headers=e)).status_code == 200  # своя видна
    my = (await client.get("/api/my/jobs", headers=e)).json()["items"]
    assert [j["id"] for j in my] == [a, c, b]


async def test_response_flow(client, pool):
    await _metro(pool)
    await _roles(client)
    e = auth(EMPLOYER)
    job = (await client.post("/api/jobs", json=job_body(), headers=e)).json()

    assert (await client.post(f"/api/jobs/{job['id']}/responses", json={}, headers=e)).status_code == 403
    resp = (await client.post(f"/api/jobs/{job['id']}/responses", json={"message": "Могу к 14:00"})).json()
    assert resp["status"] == "pending" and resp["contact"] is None and resp["worker"]["first_name"] == "Иван"
    assert (await client.post(f"/api/jobs/{job['id']}/responses", json={})).status_code == 409

    feed_item = (await client.get("/api/jobs")).json()["items"][0]
    assert feed_item["my_response"]["id"] == resp["id"] and feed_item["responses_count"] == 1

    owner_view = (await client.get(f"/api/jobs/{job['id']}", headers=e)).json()
    assert owner_view["pending_count"] == 1 and owner_view["responses"][0]["message"] == "Могу к 14:00"

    # отзыв до принятия нельзя, исполнитель не может принять сам себя
    assert (await client.post("/api/reviews", json={"response_id": resp["id"], "rating": 5})).status_code == 409
    assert (await client.patch(f"/api/responses/{resp['id']}", json={"status": "accepted"})).status_code == 403

    accepted = (await client.patch(f"/api/responses/{resp['id']}", json={"status": "accepted"}, headers=e)).json()
    assert accepted["contact"] == {"first_name": "Иван", "username": "ivan", "url": "https://t.me/ivan"}
    mine = (await client.get("/api/my/responses")).json()["items"]
    assert mine[0]["status"] == "accepted" and mine[0]["job"]["title"] == "Грузчики на Таганке"
    assert mine[0]["contact"] == {"first_name": "Ольга", "username": None, "url": f"tg://user?id={EMPLOYER}"}

    # отзывы в обе стороны, повторный заменяет
    assert (await client.post("/api/reviews", json={"response_id": resp["id"], "rating": 3})).status_code == 201
    assert (await client.post("/api/reviews", json={"response_id": resp["id"], "rating": 5,
                                                    "text": "Всё чётко"})).status_code == 201
    await client.post("/api/reviews", json={"response_id": resp["id"], "rating": 4}, headers=e)
    profile = (await client.get(f"/api/users/{EMPLOYER}")).json()
    assert profile["rating"] == 5 and profile["reviews_count"] == 1 and profile["jobs_count"] == 1
    assert profile["reviews"][0]["text"] == "Всё чётко" and profile["reviews"][0]["author"]["first_name"] == "Иван"
    assert (await client.get("/api/me")).json()["rating"] == 4
    assert (await client.get(f"/api/jobs/{job['id']}")).json()["my_response"]["my_review"] == {
        "rating": 5, "text": "Всё чётко"}

    # второй исполнитель ждёт, заказчик закрывает набор: ему приходит отказ
    other = auth(888)
    await client.patch("/api/me", json={"role": "worker"}, headers=other)
    await client.post(f"/api/jobs/{job['id']}/responses", json={}, headers=other)
    closed = (await client.patch(f"/api/jobs/{job['id']}", json={"status": "closed"}, headers=e)).json()
    assert closed["status"] == "closed" and closed["pending_count"] == 0
    assert (await client.get("/api/jobs")).json()["total"] == 0
    assert (await client.get(f"/api/jobs/{job['id']}")).status_code == 200  # откликался: видит закрытую
    assert (await client.get(f"/api/jobs/{job['id']}", headers=auth(999))).status_code == 404

    # исполнитель отказывается после принятия
    assert (await client.patch(f"/api/responses/{resp['id']}", json={"status": "withdrawn"})).json()["status"] \
        == "withdrawn"

    bot = FakeBot()
    from gigo import config
    assert await send_outbox_once(bot, pool, config.load()) == 6
    texts = [(uid, text) for uid, text in bot.sent]
    assert texts[0][0] == EMPLOYER and "Новый отклик" in texts[0][1] and "Могу к 14:00" in texts[0][1]
    assert texts[1][0] == WORKER and "Вас выбрали" in texts[1][1] and f'tg://user?id={EMPLOYER}' in texts[1][1]
    assert texts[2][0] == EMPLOYER and "@ivan" in texts[2][1]
    assert texts[4][0] == 888 and "Набор закрыт" in texts[4][1]
    assert texts[5][0] == EMPLOYER and "отказался" in texts[5][1]
    assert await send_outbox_once(bot, pool, config.load()) == 0  # повторно не шлём


async def test_subscriptions_and_notifications(client, pool):
    await _metro(pool)
    await _roles(client)
    resp = await client.post("/api/subscriptions", json={"name": "Грузчики от 400", "categories": ["loader"],
                                                         "pay_min": 400})
    assert resp.status_code == 201
    sub = resp.json()
    assert sub["categories"] == ["loader"] and sub["lat"] is None
    near = await client.post("/api/subscriptions", json={"name": "Рядом", "lat": 55.74, "lng": 37.65, "radius_km": 2})
    assert near.json()["lat"] == pytest.approx(55.74)
    assert len((await client.get("/api/subscriptions")).json()) == 2

    e = auth(EMPLOYER)
    await client.post("/api/jobs", json=job_body(), headers=e)
    await client.post("/api/jobs", json=job_body(category="courier", title="Курьер на севере", pay_amount=350,
                                                 metro_id="2.1"), headers=e)

    from gigo import config
    bot = FakeBot()
    since = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert await notify_once(bot, pool, config.load(), since) == 1  # обе подписки ловят заявку, но письмо одно
    assert bot.sent[0][0] == WORKER and "Грузчики на Таганке" in bot.sent[0][1] and "500 ₽/ч" in bot.sent[0][1]
    assert await notify_once(bot, pool, config.load(), since) == 0  # повторно не шлём

    assert (await client.delete(f"/api/subscriptions/{sub['id']}")).status_code == 204
    assert len((await client.get("/api/subscriptions")).json()) == 1
