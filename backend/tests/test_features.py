"""Поиск, избранное, навыки исполнителя и правка заявки."""

from gigo import config
from gigo.bot.__main__ import send_outbox_once

from tests.test_api import EMPLOYER, WORKER, FakeBot, _metro, _roles, auth, client, job_body  # noqa: F401


async def test_search(client, pool):
    await _metro(pool)
    await _roles(client)
    e = auth(EMPLOYER)
    a = (await client.post("/api/jobs", json=job_body(description="Мебель, лифт есть"), headers=e)).json()["id"]
    b = (await client.post("/api/jobs", json=job_body(category="courier", title="Доставка документов",
                                                      metro_id="2.1"), headers=e)).json()["id"]

    def ids(q):
        return client.get("/api/jobs", params={"q": q})

    assert [j["id"] for j in (await ids("лифт")).json()["items"]] == [a]
    assert [j["id"] for j in (await ids("курьер")).json()["items"]] == [b]  # по названию категории
    assert [j["id"] for j in (await ids("речной")).json()["items"]] == [b]  # по метро
    assert (await ids("доставка таганская")).json()["total"] == 0  # все слова сразу
    assert (await ids("100%")).json()["total"] == 0  # % не шаблон
    assert (await ids("   ")).json()["total"] == 2


async def test_saved_jobs(client, pool):
    await _metro(pool)
    await _roles(client)
    e = auth(EMPLOYER)
    a = (await client.post("/api/jobs", json=job_body(), headers=e)).json()["id"]
    b = (await client.post("/api/jobs", json=job_body(title="Второй переезд"), headers=e)).json()["id"]

    assert (await client.put(f"/api/jobs/{a}/save")).status_code == 204
    assert (await client.put(f"/api/jobs/{b}/save")).status_code == 204
    assert (await client.put(f"/api/jobs/{b}/save")).status_code == 204  # повторно без ошибки
    assert (await client.put("/api/jobs/999999/save")).status_code == 404
    saved = (await client.get("/api/my/saved")).json()["items"]
    assert [j["id"] for j in saved] == [b, a] and all(j["is_saved"] for j in saved)
    feed = (await client.get("/api/jobs")).json()["items"]
    assert all(j["is_saved"] for j in feed)
    assert not (await client.get("/api/jobs", headers=auth(888))).json()["items"][0]["is_saved"]

    assert (await client.delete(f"/api/jobs/{a}/save")).status_code == 204
    assert [j["id"] for j in (await client.get("/api/my/saved")).json()["items"]] == [b]
    # скрытая модератором пропадает из избранного
    await pool.execute("UPDATE jobs SET hidden_at = now() WHERE id = $1", b)
    assert (await client.get("/api/my/saved")).json()["items"] == []


async def test_skills(client, pool):
    await _metro(pool)
    await _roles(client)
    me = (await client.patch("/api/me", json={"skills": ["driver", "loader", "nope", "loader"]})).json()
    assert me["skills"] == ["loader", "driver"]
    assert (await client.get(f"/api/users/{WORKER}")).json()["skills"] == ["loader", "driver"]
    e = auth(EMPLOYER)
    job = (await client.post("/api/jobs", json=job_body(), headers=e)).json()
    await client.post(f"/api/jobs/{job['id']}/responses", json={})
    owner = (await client.get(f"/api/jobs/{job['id']}", headers=e)).json()
    assert owner["responses"][0]["worker"]["skills"] == ["loader", "driver"]
    assert (await client.patch("/api/me", json={"skills": []})).json()["skills"] == []


async def test_edit_job(client, pool):
    await _metro(pool)
    await _roles(client)
    e = auth(EMPLOYER)
    job = (await client.post("/api/jobs", json=job_body(workers_needed=2), headers=e)).json()
    jid = job["id"]
    resp = (await client.post(f"/api/jobs/{jid}/responses", json={})).json()
    await client.patch(f"/api/responses/{resp['id']}", json={"status": "accepted"}, headers=e)

    assert (await client.put(f"/api/jobs/{jid}", json=job_body(title="Чужая"))).status_code == 404
    bad = await client.put(f"/api/jobs/{jid}", json=job_body(title="Нужны кладмены"), headers=e)
    assert bad.status_code == 422
    fewer = await client.put(f"/api/jobs/{jid}", json=job_body(workers_needed=0), headers=e)
    assert fewer.status_code == 422

    upd = (await client.put(f"/api/jobs/{jid}", json=job_body(title="Грузчики, 3 часа", pay_amount=700,
                                                               metro_id="2.1", workers_needed=1), headers=e)).json()
    assert upd["title"] == "Грузчики, 3 часа" and upd["pay_per_hour"] == 700 and upd["metro"]["id"] == "2.1"
    assert upd["lat"] > 55.8 and upd["accepted_count"] == 1 and upd["responses"][0]["status"] == "accepted"

    bot = FakeBot()
    await send_outbox_once(bot, pool, config.load())
    assert any(uid == WORKER and "изменил заявку «Грузчики, 3 часа»" in text for uid, text in bot.sent)

    await client.patch(f"/api/jobs/{jid}", json={"status": "closed"}, headers=e)
    assert (await client.put(f"/api/jobs/{jid}", json=job_body(), headers=e)).status_code == 409


async def test_workers_catalog_and_invites(client, pool):
    await _metro(pool)
    await _roles(client)
    e = auth(EMPLOYER)
    await client.patch("/api/me", json={"skills": ["loader"], "about": "Сильный"})
    silent = auth(888)
    await client.patch("/api/me", json={"role": "worker"}, headers=silent)  # пустой профиль: не в каталоге

    assert (await client.get("/api/workers")).status_code == 403  # каталог для заказчика
    cat = (await client.get("/api/workers", headers=e)).json()
    assert cat["total"] == 1 and cat["items"][0]["id"] == WORKER and cat["items"][0]["skills"] == ["loader"]
    assert (await client.get("/api/workers", params={"category": "driver"}, headers=e)).json()["total"] == 0
    assert (await client.get("/api/workers", params={"q": "сильн"}, headers=e)).json()["total"] == 1

    job = (await client.post("/api/jobs", json=job_body(), headers=e)).json()
    url = f"/api/jobs/{job['id']}/invites"
    assert (await client.post(url, json={"worker_id": WORKER})).status_code == 404  # чужая заявка
    assert (await client.post(url, json={"worker_id": EMPLOYER}, headers=e)).status_code == 404  # не исполнитель
    assert (await client.post(url, json={"worker_id": WORKER}, headers=e)).status_code == 204
    assert (await client.post(url, json={"worker_id": WORKER}, headers=e)).status_code == 409  # повторно
    assert (await client.get(f"/api/users/{WORKER}", headers=e)).json()["invited_job_ids"] == [job["id"]]
    assert (await client.get(f"/api/jobs/{job['id']}")).json()["is_invited"] is True

    await client.post(f"/api/jobs/{job['id']}/responses", json={}, headers=silent)
    assert (await client.post(url, json={"worker_id": 888}, headers=e)).status_code == 409  # уже откликнулся

    bot = FakeBot()
    await send_outbox_once(bot, pool, config.load())
    assert any(uid == WORKER and "приглашает вас" in text for uid, text in bot.sent)
