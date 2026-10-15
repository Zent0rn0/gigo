"""Единый вид ошибок, сбои базы, лимиты тела и времени ответа."""

import asyncio
import json

import asyncpg
import httpx
import pytest

from gigo.api.auth import InitDataError, validate_init_data
from gigo.api.errors import GuardMiddleware, validation_message
from gigo.geo import Geocoder
from tests.test_api import BOT_TOKEN, EMPLOYER, _metro, _roles, auth, job_body


@pytest.fixture
async def app_client(pool, monkeypatch):
    """Клиент, который не пробрасывает исключения приложения: проверяем, что видит Mini App."""
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("DEV_AUTH", "0")
    monkeypatch.delenv("YANDEX_GEOCODER_KEY", raising=False)
    from gigo.api.app import app, mutations

    mutations.hits.clear()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=auth()) as c:
            yield app, c


def assert_error(resp, status, code=None):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert isinstance(body["detail"], str) and body["detail"]
    assert body["request_id"] and resp.headers["x-request-id"] == body["request_id"]
    if code:
        assert body["code"] == code
    assert "Traceback" not in resp.text
    return body


async def test_validation_is_human_text(app_client):
    _, c = app_client
    body = assert_error(await c.patch("/api/me", json={"role": "boss"}), 422, "invalid")
    assert body["detail"] == "Роль: недопустимое значение"
    assert body["errors"][0]["loc"] == ["body", "role"] and "input" not in body["errors"][0]
    body = assert_error(await c.post("/api/subscriptions", json={"name": "x" * 101}), 422)
    assert body["detail"] == "Название: не длиннее 100 знаков"
    # сломанный JSON и NaN
    resp = await c.patch("/api/me", content=b"{oops", headers={"Content-Type": "application/json"})
    assert assert_error(resp, 422)["detail"] == "Неверный формат запроса"
    resp = await c.post("/api/subscriptions", content=b'{"name": "a", "pay_min": NaN}',
                        headers={"Content-Type": "application/json"})
    assert_error(resp, 422)
    assert_error(await c.get("/api/jobs?pay_min=nan"), 422)
    assert_error(await c.get("/api/jobs?lat=inf&lng=37"), 422)
    assert_error(await c.get("/api/jobs?" + "&".join(["category=x"] * 51)), 422)


def test_validation_message_fallbacks():
    assert validation_message([]) == "Проверьте введённые данные"
    assert validation_message([{"type": "missing", "loc": ("body", "unknown_field")}]) == \
        "Проверьте введённые данные: заполните это поле"


async def test_not_found_and_overflow(app_client):
    _, c = app_client
    assert assert_error(await c.get("/api/nope"), 404, "not_found")["detail"] == "Не найдено"
    assert_error(await c.delete("/api/me"), 405, "method_not_allowed")
    # id больше bigint: не 500, а понятная ошибка
    assert_error(await c.get("/api/jobs/99999999999999999999999"), 422)
    assert_error(await c.patch("/api/responses/9223372036854775808", json={"status": "withdrawn"}), 422)
    assert_error(await c.post("/api/reviews", json={"response_id": 2**70, "rating": 5}), 422)


async def test_body_too_large(app_client):
    _, c = app_client
    big = json.dumps({"about": "я" * 100_000})
    assert_error(await c.patch("/api/me", content=big, headers={"Content-Type": "application/json"}), 413,
                 "too_large")

    async def chunks():  # без Content-Length: считаем по ходу чтения
        for _ in range(100):
            yield b"x" * 1024

    assert_error(await c.patch("/api/me", content=chunks(), headers={"Content-Type": "application/json"}), 413)


async def test_auth_garbage_is_401(app_client):
    _, c = app_client
    resp = await c.get("/api/me", headers={"Authorization": "tma auth_date=abc&hash=1"})
    assert_error(resp, 401, "unauthorized")
    with pytest.raises(InitDataError):
        validate_init_data("auth_date=abc&hash=00", BOT_TOKEN)


async def test_unexpected_error_hides_details(app_client, monkeypatch):
    app, c = app_client
    import gigo.api.app as api

    def boom(_):
        raise RuntimeError("секрет из трассировки")

    monkeypatch.setattr(api, "me_out", boom)
    resp = await c.get("/api/me", headers={"X-Request-ID": "abc-123"})
    body = assert_error(resp, 500, "internal")
    assert body["request_id"] == "abc-123" and "секрет" not in resp.text


class BrokenPool:
    """Пул, у которого база «упала»."""

    def __init__(self, real, exc):
        self.real, self.exc = real, exc

    async def _fail(self, *a, **kw):
        raise self.exc

    fetchrow = fetchval = fetch = execute = _fail

    def acquire(self):
        raise self.exc

    def __getattr__(self, name):
        return getattr(self.real, name)


@pytest.mark.parametrize("exc", [ConnectionRefusedError(111, "refused"), asyncpg.CannotConnectNowError("starting"),
                                 asyncpg.TooManyConnectionsError("too many"), TimeoutError()])
async def test_database_down_is_503(app_client, exc):
    app, c = app_client
    real = app.state.pool
    app.state.pool = BrokenPool(real, exc)
    try:
        body = assert_error(await c.get("/api/me"), 503)
        assert body["code"] in ("db_unavailable", "db_busy", "unavailable")
        resp = await c.get("/api/health")
        assert resp.status_code == 503 and resp.json()["ok"] is False
    finally:
        app.state.pool = real
    assert (await c.get("/api/health")).json() == {"ok": True}


async def test_statement_timeout_is_503(app_client, monkeypatch):
    _, c = app_client
    import gigo.api.app as api

    monkeypatch.setattr(api, "me_out", lambda r: (_ for _ in ()).throw(asyncpg.QueryCanceledError("timeout")))
    assert_error(await c.get("/api/me"), 503, "db_busy")


async def test_check_violation_is_422(app_client, monkeypatch):
    app, c = app_client
    import gigo.api.app as api

    monkeypatch.setattr(api, "me_out", lambda r: (_ for _ in ()).throw(asyncpg.CheckViolationError("check")))
    assert_error(await c.get("/api/me"), 422, "invalid")
    monkeypatch.setattr(api, "me_out", lambda r: (_ for _ in ()).throw(asyncpg.UniqueViolationError("dup")))
    assert_error(await c.get("/api/me"), 409, "duplicate")


async def test_request_timeout():
    async def slow_app(scope, receive, send):
        await asyncio.sleep(5)

    guard = GuardMiddleware(slow_app, timeout=0.05)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=guard), base_url="http://t") as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 503 and resp.json()["code"] == "timeout" and resp.headers["x-request-id"]


async def test_db_pool_settings(pool):
    assert await pool.fetchval("SHOW idle_in_transaction_session_timeout") == "1min"
    assert await pool.fetchval("SHOW statement_timeout") == "20s"
    with pytest.raises(asyncpg.QueryCanceledError):
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 50")
            await conn.execute("SELECT pg_sleep(1)")


async def test_geocoder_failure_does_not_break_job(app_client, pool):
    app, c = app_client

    class Boom:
        async def fetchrow(self, *a):
            raise RuntimeError("кэш сломался")

    geo = Geocoder("key", Boom())
    assert await geo.locate("Тверская, 1") is None
    await geo.close()

    await _metro(pool)
    await _roles(c)
    real = app.state.geocoder
    app.state.geocoder = geo
    try:
        resp = await c.post("/api/jobs", json=job_body(address="Тверская, 1"), headers=auth(EMPLOYER))
        assert resp.status_code == 201, resp.text
    finally:
        app.state.geocoder = real
