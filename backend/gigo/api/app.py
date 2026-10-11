"""HTTP API для Mini App. Контракт: docs/api.md.

    uvicorn gigo.api.app:app --port 8000
"""

import logging
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from gigo import actions, config, db, events, rules
from gigo.api.auth import InitDataError, TgUser, validate_init_data
from gigo.api.limits import RateLimiter, check_recent
from gigo.categories import CATEGORIES, PAY_UNITS, SCAM_FLAGS
from gigo.geo import Geocoder
from gigo.jobs_query import JobFilter, build_feed, jobs_where, rating_join, responses_where
from gigo.migrate import migrate

log = logging.getLogger("gigo.api")

CITY = {"id": "moscow", "name": "Москва", "lat": 55.7558, "lng": 37.6176}
MAX_SUBSCRIPTIONS = 10
MAX_OPEN_JOBS = 20
MAX_DAYS_AHEAD = 60
STATIC_DIR = Path(os.getenv("STATIC_DIR", config.ROOT / "frontend" / "dist"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = config.load()
    await migrate(settings.database_url)
    app.state.settings = settings
    app.state.pool = await db.connect(settings.database_url)
    app.state.geocoder = Geocoder(settings.yandex_geocoder_key, app.state.pool, CITY["name"])
    if not settings.bot_token and not settings.dev_auth:
        log.warning("BOT_TOKEN не задан: вход из Mini App работать не будет")
    yield
    await app.state.pool.close()


# Документация API открыта только в режиме разработки.
_DEV = config.load().dev_auth
app = FastAPI(title="Gigo", lifespan=lifespan, docs_url="/api/docs" if _DEV else None,
              redoc_url=None, openapi_url="/api/openapi.json" if _DEV else None)

mutations = RateLimiter(limit=60, window=60)


@app.exception_handler(actions.ActionError)
async def action_error(request: Request, e: actions.ActionError):
    return JSONResponse({"detail": e.detail}, status_code=e.status)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# --- вход ---------------------------------------------------------------

@dataclass(frozen=True)
class Me:
    id: int
    username: str | None
    first_name: str | None
    role: str | None


_FORWARD_HEADERS = ("x-forwarded-for", "x-real-ip", "cf-connecting-ip", "forwarded")


def _is_local(request: Request) -> bool:
    """Запрос пришёл с этой же машины напрямую, не через туннель или прокси."""
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost") and not any(h in request.headers for h in _FORWARD_HEADERS)


async def current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_dev_user: Annotated[int | None, Header()] = None,
) -> Me:
    settings: config.Settings = request.app.state.settings
    if authorization and authorization.startswith("tma ") and settings.bot_token:
        try:
            user = validate_init_data(authorization[4:], settings.bot_token)
        except InitDataError as e:
            raise HTTPException(401, f"Вход не подтверждён: {e}")
    elif settings.dev_auth and _is_local(request):
        # Вход без Telegram только с этой же машины: через туннель или прокси так не войти.
        uid = x_dev_user or 1
        user = TgUser(uid, f"dev{uid}", f"Разработчик {uid}")
    else:
        raise HTTPException(401, "Откройте приложение из Telegram")
    row = await request.app.state.pool.fetchrow(
        """INSERT INTO users (tg_id, username, first_name) VALUES ($1, $2, $3)
           ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username, first_name = EXCLUDED.first_name,
               last_seen_at = now()
           RETURNING tg_id, username, first_name, role, banned_at""",
        user.id, user.username, (user.first_name or "")[:64] or None,
    )
    if row["banned_at"]:
        raise HTTPException(403, "Аккаунт заблокирован за нарушение правил Gigo. "
                                 "Если это ошибка, напишите боту.")
    if request.method != "GET" and not mutations.hit(user.id):
        raise HTTPException(429, "Слишком много действий подряд. Подождите минуту.")
    return Me(row["tg_id"], row["username"], row["first_name"], row["role"])


User = Annotated[Me, Depends(current_user)]


def require_role(user: Me, role: str) -> None:
    if user.role != role:
        who = "заказчика" if role == "employer" else "исполнителя"
        raise HTTPException(403, f"Это действие для {who}. Роль меняется в профиле.")


def _num(v):
    return float(v) if v is not None else None


def _ts(v):
    return v.isoformat() if v is not None else None


def pool(request: Request):
    return request.app.state.pool


@app.get("/api/health")
async def health(request: Request):
    await pool(request).fetchval("SELECT 1")
    return {"ok": True}


# --- профиль ------------------------------------------------------------

ME_SQL = f"""
SELECT u.tg_id, u.username, u.first_name, u.role, u.about, ur.rating, ur.reviews_count
FROM users u {rating_join("ur", "u.tg_id")} WHERE u.tg_id = $1
"""


def me_out(r) -> dict:
    return {"id": r["tg_id"], "username": r["username"], "first_name": r["first_name"], "role": r["role"],
            "about": r["about"], "rating": _num(r["rating"]), "reviews_count": r["reviews_count"]}


@app.get("/api/me")
async def get_me(request: Request, user: User):
    return me_out(await pool(request).fetchrow(ME_SQL, user.id))


class MeIn(BaseModel):
    role: Literal["employer", "worker"] | None = None
    about: str | None = Field(default=None, max_length=500)


@app.patch("/api/me")
async def patch_me(request: Request, body: MeIn, user: User):
    fields = body.model_dump(exclude_unset=True)
    if "role" in fields and fields["role"] is None:
        raise HTTPException(422, "Выберите роль")
    if "about" in fields:
        fields["about"] = _clean(fields["about"])
    if fields:
        sets = ", ".join(f"{k} = ${i}" for i, k in enumerate(fields, start=2))
        await pool(request).execute(f"UPDATE users SET {sets} WHERE tg_id = $1", user.id, *fields.values())
    return me_out(await pool(request).fetchrow(ME_SQL, user.id))


@app.get("/api/users/{user_id}")
async def get_user(request: Request, user_id: int, _: User):
    p = pool(request)
    r = await p.fetchrow(ME_SQL, user_id)
    if not r:
        raise HTTPException(404, "Пользователь не найден")
    if r["role"] == "worker":
        jobs_count = await p.fetchval(
            "SELECT count(*) FROM responses WHERE worker_id = $1 AND status = 'accepted'", user_id)
    else:
        jobs_count = await p.fetchval("SELECT count(*) FROM jobs WHERE employer_id = $1", user_id)
    reviews = await p.fetch(
        """SELECT rv.rating, rv.text, rv.created_at, a.tg_id AS author_id, a.first_name AS author_name,
                  j.title AS job_title
           FROM reviews rv JOIN users a ON a.tg_id = rv.author_id JOIN jobs j ON j.id = rv.job_id
           WHERE rv.target_id = $1 ORDER BY rv.created_at DESC LIMIT 50""",
        user_id,
    )
    return {
        "id": r["tg_id"], "first_name": r["first_name"], "role": r["role"], "about": r["about"],
        "rating": _num(r["rating"]), "reviews_count": r["reviews_count"], "jobs_count": jobs_count,
        "reviews": [{"rating": v["rating"], "text": v["text"], "job_title": v["job_title"],
                     "author": {"id": v["author_id"], "first_name": v["author_name"]},
                     "created_at": _ts(v["created_at"])} for v in reviews],
    }


# --- справочники ----------------------------------------------------------

@app.get("/api/meta")
async def meta(request: Request, _: User):
    rows = await pool(request).fetch(
        "SELECT id, name, line, line_color, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
        "FROM metro_stations WHERE city = $1 ORDER BY name, id", CITY["id"],
    )
    return {
        "categories": [{"id": k, "label": label, "emoji": emoji} for k, (label, emoji) in CATEGORIES.items()],
        "pay_units": [{"id": k, "label": label} for k, label in PAY_UNITS.items()],
        "metro": [{"id": r["id"], "name": r["name"], "line": r["line"],
                   "color": f"#{r['line_color']}" if r["line_color"] else None, "lat": r["lat"], "lng": r["lng"]}
                  for r in rows],
        "city": CITY,
    }


# --- отклики: вид -----------------------------------------------------------

def response_out(r, viewer_id: int) -> dict:
    contact = None
    if r["status"] == "accepted":
        if viewer_id == r["employer_id"]:
            uid, name, username = r["worker_id"], r["worker_name"], r["worker_username"]
        else:
            uid, name, username = r["employer_id"], r["employer_name"], r["employer_username"]
        contact = {"first_name": name, "username": username, "url": events.contact_url(uid, username)}
    return {
        "id": r["id"],
        "job_id": r["job_id"],
        "status": r["status"],
        "message": r["message"],
        "created_at": _ts(r["created_at"]),
        "worker": {"id": r["worker_id"], "first_name": r["worker_name"], "about": r["worker_about"],
                   "rating": _num(r["worker_rating"]), "reviews_count": r["worker_reviews"]},
        "contact": contact,
        "my_review": {"rating": r["my_rating"], "text": r["my_text"]} if r["my_rating"] is not None else None,
    }


async def fetch_responses(p, viewer_id: int, where: str, *args) -> list[dict]:
    rows = await p.fetch(responses_where(where), viewer_id, *args)
    return [response_out(r, viewer_id) for r in rows]


# --- заявки: вид ----------------------------------------------------------

def job_out(r, my_response: dict | None = None) -> dict:
    out = {
        "id": r["id"],
        "status": r["status"],
        "category": r["category"],
        "title": r["title"],
        "description": r["description"],
        "workers_needed": r["workers_needed"],
        "pay_amount": _num(r["pay_amount"]),
        "pay_unit": r["pay_unit"],
        "pay_per_hour": _num(r["pay_per_hour"]),
        "pay_estimated": r["pay_estimated"],
        "pay_total": _num(r["pay_total"]),
        "pay_timing": r["pay_timing"],
        "starts_on": r["starts_on"].isoformat() if r["starts_on"] else None,
        "starts_at": _ts(r["starts_at"]),
        "duration_hours": _num(r["duration_hours"]),
        "metro": {"id": r["metro_id"], "name": r["metro_name"], "line": r["metro_line"],
                  "color": f"#{r['metro_color']}" if r["metro_color"] else None} if r["metro_id"] else None,
        "address": r["address"],
        "lat": r["lat"],
        "lng": r["lng"],
        "distance_km": round(r["distance_km"], 1) if r["distance_km"] is not None else None,
        "employer": {"id": r["employer_id"], "first_name": r["employer_name"],
                     "rating": _num(r["employer_rating"]), "reviews_count": r["employer_reviews"]},
        "responses_count": r["responses_count"],
        "accepted_count": r["accepted_count"],
        "is_mine": r["is_mine"],
        "my_response": my_response,
        "created_at": _ts(r["created_at"]),
        "expires_at": _ts(r["expires_at"]),
    }
    if r["is_mine"]:
        out["pending_count"] = r["pending_count"]
    return out


async def jobs_with_my_responses(p, user: Me, rows) -> list[dict]:
    ids = [r["id"] for r in rows]
    mine = {}
    if ids:
        for resp in await fetch_responses(p, user.id, "r.worker_id = $1 AND r.job_id = ANY($2::bigint[])", ids):
            mine[resp["job_id"]] = resp
    return [job_out(r, mine.get(r["id"])) for r in rows]


async def load_job(p, user: Me, job_id: int) -> dict:
    row = await p.fetchrow(jobs_where("j.id = $2"), user.id, job_id)
    if not row:
        raise HTTPException(404, "Заявка не найдена")
    [job] = await jobs_with_my_responses(p, user, [row])
    visible = (row["status"] == "open" and row["expires_at"] > datetime.now(timezone.utc)
               and row["hidden_at"] is None) or job["is_mine"] or job["my_response"]
    if not visible:
        raise HTTPException(404, "Заявка закрыта")
    if job["is_mine"]:
        job["responses"] = await fetch_responses(p, user.id, "r.job_id = $2", job_id)
    return job


# --- заявки: лента и карточка ------------------------------------------------

@app.get("/api/jobs")
async def list_jobs(
    request: Request,
    user: User,
    category: Annotated[list[str], Query()] = [],
    pay_min: float | None = None,
    metro: Annotated[list[str], Query()] = [],
    today: bool = False,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_km: Annotated[float | None, Query(gt=0, le=100)] = None,
    sort: Annotated[str, Query(pattern="^(fresh|distance|pay)$")] = "fresh",
    with_location: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    f = JobFilter(category, pay_min, metro, today, lat, lng, radius_km, with_location, sort, limit, offset)
    list_sql, count_sql, params = build_feed(f, user.id)
    p = pool(request)
    rows = await p.fetch(list_sql, *params)
    total = await p.fetchval(count_sql, *params)
    return {"total": total, "items": await jobs_with_my_responses(p, user, rows)}


@app.get("/api/jobs/{job_id}")
async def get_job(request: Request, job_id: int, user: User):
    return await load_job(pool(request), user, job_id)


@app.get("/api/my/jobs")
async def my_jobs(request: Request, user: User):
    p = pool(request)
    rows = await p.fetch(jobs_where("j.employer_id = $1",
                                    "(j.status = 'open' AND j.expires_at > now()) DESC, j.created_at DESC"), user.id)
    return {"items": [job_out(r) for r in rows]}


# --- заявки: создание и статус ------------------------------------------------

class JobIn(BaseModel):
    category: str
    title: str = Field(min_length=3, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    workers_needed: int = Field(default=1, ge=1, le=50)
    pay_amount: float = Field(gt=0, le=1_000_000)
    pay_unit: str
    pay_timing: str | None = Field(default=None, max_length=50)
    starts_on: date | None = None
    start_time: str | None = Field(default=None, pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    duration_hours: float | None = Field(default=None, gt=0, le=24)
    metro_id: str | None = None
    address: str | None = Field(default=None, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


def _clean(s: str | None) -> str | None:
    """Без управляющих символов и подмены направления текста; пустая строка → None."""
    return _CONTROL.sub("", s or "").strip() or None


@app.post("/api/jobs", status_code=201)
async def create_job(request: Request, body: JobIn, user: User):
    require_role(user, "employer")
    p = pool(request)
    if body.category not in CATEGORIES:
        raise HTTPException(422, "Неизвестная категория")
    if body.pay_unit not in PAY_UNITS:
        raise HTTPException(422, "Неизвестная единица оплаты")
    title, description, address = _clean(body.title), _clean(body.description), _clean(body.address)
    if not title:
        raise HTTPException(422, "Напишите, что нужно сделать")
    if flags := rules.scam_flags(f"{title}\n{description or ''}"):
        raise HTTPException(422, f"Заявку нельзя опубликовать: {SCAM_FLAGS[flags[0]]}. "
                                 "Если это ошибка, переформулируйте текст.")
    has_point = body.lat is not None and body.lng is not None
    if not (body.metro_id or address or has_point):
        raise HTTPException(422, "Укажите метро или адрес")
    if await p.fetchval("SELECT count(*) FROM jobs WHERE employer_id = $1 AND status = 'open' AND expires_at > now()",
                        user.id) >= MAX_OPEN_JOBS:
        raise HTTPException(409, f"Открыто уже {MAX_OPEN_JOBS} заявок. Закройте ненужные, чтобы создать новую.")
    await check_recent(p, "SELECT count(*) FROM jobs WHERE employer_id = $1 AND created_at > now() - interval '1 hour'",
                       user.id, 5, "Не больше 5 заявок в час. Попробуйте позже.")

    now = datetime.now(rules.MSK)
    day = body.starts_on
    at = time.fromisoformat(body.start_time.zfill(5)) if body.start_time else None
    if at and not day:
        day = now.date()
    if day and not (now.date() <= day <= now.date() + timedelta(days=MAX_DAYS_AHEAD)):
        raise HTTPException(422, f"Дата должна быть от сегодня до {MAX_DAYS_AHEAD} дней вперёд")
    start = rules.starts_at(day, at)
    if start and start < now - timedelta(minutes=30):
        raise HTTPException(422, "Время начала уже прошло")

    metro = None
    if body.metro_id:
        metro = await p.fetchrow("SELECT ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
                                 "FROM metro_stations WHERE id = $1", body.metro_id)
        if not metro:
            raise HTTPException(422, "Неизвестная станция метро")
    point = (body.lat, body.lng) if has_point else None
    if not point and address:
        point = await request.app.state.geocoder.locate(address)
    if not point and metro:
        point = (metro["lat"], metro["lng"])

    per_hour, estimated = rules.pay_per_hour(body.pay_amount, body.pay_unit, body.duration_hours)
    job_id = await p.fetchval(
        """INSERT INTO jobs (employer_id, category, title, description, workers_needed, pay_amount, pay_unit,
                             pay_per_hour, pay_estimated, pay_total, pay_timing, starts_on, starts_at, duration_hours,
                             metro_id, address, location, expires_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                   CASE WHEN $17::float8 IS NULL THEN NULL
                        ELSE ST_SetSRID(ST_MakePoint($18, $17), 4326)::geography END, $19)
           RETURNING id""",
        user.id, body.category, title, description, body.workers_needed, body.pay_amount, body.pay_unit,
        per_hour, estimated, rules.pay_total(body.pay_amount, body.pay_unit, body.duration_hours),
        _clean(body.pay_timing), day, start, body.duration_hours, body.metro_id, address,
        point[0] if point else None, point[1] if point else None,
        rules.expires_at(now, day, start),
    )
    return await load_job(p, user, job_id)


class JobStatusIn(BaseModel):
    status: Literal["open", "closed", "cancelled"]


@app.patch("/api/jobs/{job_id}")
async def update_job(request: Request, job_id: int, body: JobStatusIn, user: User):
    p = pool(request)
    async with p.acquire() as conn, conn.transaction():
        await actions.set_job_status(conn, job_id, user.id, body.status)
    return await load_job(p, user, job_id)


# --- отклики: действия ------------------------------------------------------

class ResponseIn(BaseModel):
    message: str | None = Field(default=None, max_length=500)


@app.post("/api/jobs/{job_id}/responses", status_code=201)
async def respond(request: Request, job_id: int, body: ResponseIn, user: User):
    require_role(user, "worker")
    p = pool(request)
    message = _clean(body.message)
    async with p.acquire() as conn, conn.transaction():
        job = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
        if not job:
            raise HTTPException(404, "Заявка не найдена")
        if job["employer_id"] == user.id:
            raise HTTPException(409, "Это ваша заявка")
        if job["status"] != "open" or job["expires_at"] <= datetime.now(timezone.utc) or job["hidden_at"]:
            raise HTTPException(409, "Набор на эту заявку закрыт")
        await check_recent(conn, "SELECT count(*) FROM responses WHERE worker_id = $1 "
                                 "AND updated_at > now() - interval '1 hour'",
                           user.id, 30, "Слишком много откликов за час. Попробуйте позже.")
        resp_id = await conn.fetchval(
            """INSERT INTO responses (job_id, worker_id, message) VALUES ($1, $2, $3)
               ON CONFLICT (job_id, worker_id) DO UPDATE
                   SET status = 'pending', message = EXCLUDED.message, updated_at = now()
                   WHERE responses.status = 'withdrawn'
               RETURNING id""",
            job_id, user.id, message,
        )
        if not resp_id:
            raise HTTPException(409, "Вы уже откликнулись")
        worker = await conn.fetchrow("SELECT tg_id, first_name, username FROM users WHERE tg_id = $1", user.id)
        await events.new_response(conn, job, worker, message, resp_id)
    [resp] = await fetch_responses(p, user.id, "r.id = $2", resp_id)
    return resp


class ResponseStatusIn(BaseModel):
    status: Literal["accepted", "rejected", "withdrawn"]


@app.patch("/api/responses/{response_id}")
async def update_response(request: Request, response_id: int, body: ResponseStatusIn, user: User):
    p = pool(request)
    async with p.acquire() as conn, conn.transaction():
        await actions.set_response_status(conn, response_id, user.id, body.status)
    [resp] = await fetch_responses(p, user.id, "r.id = $2", response_id)
    return resp


@app.get("/api/my/responses")
async def my_responses(request: Request, user: User):
    p = pool(request)
    responses = await fetch_responses(p, user.id, "r.worker_id = $1")
    rows = await p.fetch(jobs_where("j.id = ANY($2::bigint[])"), user.id, list({r["job_id"] for r in responses}))
    jobs = {r["id"]: job_out(r) for r in rows}
    return {"items": [{**resp, "job": jobs[resp["job_id"]]} for resp in responses]}


# --- жалобы ---------------------------------------------------------------

class ReportIn(BaseModel):
    reason: Literal["scam", "spam", "rude", "other"]
    text: str | None = Field(default=None, max_length=500)


@app.post("/api/jobs/{job_id}/report", status_code=204)
async def report_job(request: Request, job_id: int, body: ReportIn, user: User):
    p = pool(request)
    async with p.acquire() as conn, conn.transaction():
        await check_recent(conn, "SELECT count(*) FROM reports WHERE author_id = $1 "
                                 "AND created_at > now() - interval '1 day'",
                           user.id, 10, "Не больше 10 жалоб в сутки.")
        await actions.report_job(conn, job_id, user.id, body.reason, _clean(body.text),
                                 request.app.state.settings.admin_ids)
    return Response(status_code=204)


# --- отзывы ---------------------------------------------------------------

class ReviewIn(BaseModel):
    response_id: int
    rating: int = Field(ge=1, le=5)
    text: str | None = Field(default=None, max_length=1000)


@app.post("/api/reviews", status_code=201)
async def create_review(request: Request, body: ReviewIn, user: User):
    p = pool(request)
    r = await p.fetchrow(
        "SELECT r.job_id, r.worker_id, r.status, j.employer_id FROM responses r JOIN jobs j ON j.id = r.job_id "
        "WHERE r.id = $1", body.response_id)
    if not r or user.id not in (r["worker_id"], r["employer_id"]):
        raise HTTPException(404, "Отклик не найден")
    if r["status"] != "accepted":
        raise HTTPException(409, "Отзыв можно оставить только после того, как отклик принят")
    target = r["worker_id"] if user.id == r["employer_id"] else r["employer_id"]
    text = _clean(body.text)
    await p.execute(
        """INSERT INTO reviews (job_id, author_id, target_id, rating, text) VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (job_id, author_id, target_id) DO UPDATE
               SET rating = EXCLUDED.rating, text = EXCLUDED.text, created_at = now()""",
        r["job_id"], user.id, target, body.rating, text,
    )
    return {"rating": body.rating, "text": text}


# --- подписки -----------------------------------------------------------

class SubscriptionIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    categories: list[str] = []
    pay_min: float | None = Field(default=None, ge=0)
    metro_ids: list[str] = []
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=100)
    today_only: bool = False


_SUB_COLUMNS = """id, name, categories, pay_min, metro_ids, ST_Y(location::geometry) AS lat,
                  ST_X(location::geometry) AS lng, radius_km, today_only, enabled"""


def sub_out(r) -> dict:
    d = dict(r)
    d["pay_min"] = _num(d["pay_min"])
    d["radius_km"] = _num(d["radius_km"])
    return d


@app.get("/api/subscriptions")
async def list_subscriptions(request: Request, user: User):
    rows = await pool(request).fetch(
        f"SELECT {_SUB_COLUMNS} FROM subscriptions WHERE user_id = $1 ORDER BY id", user.id
    )
    return [sub_out(r) for r in rows]


@app.post("/api/subscriptions", status_code=201)
async def create_subscription(request: Request, body: SubscriptionIn, user: User):
    p = pool(request)
    if await p.fetchval("SELECT count(*) FROM subscriptions WHERE user_id = $1", user.id) >= MAX_SUBSCRIPTIONS:
        raise HTTPException(409, f"Можно не больше {MAX_SUBSCRIPTIONS} подписок")
    categories = [c for c in body.categories if c in CATEGORIES]
    has_point = body.lat is not None and body.lng is not None
    row = await p.fetchrow(
        f"""INSERT INTO subscriptions (user_id, name, categories, pay_min, metro_ids, location, radius_km, today_only)
            VALUES ($1, $2, $3, $4, $5,
                    CASE WHEN $6::bool THEN ST_SetSRID(ST_MakePoint($7, $8), 4326)::geography END, $9, $10)
            RETURNING {_SUB_COLUMNS}""",
        user.id, body.name, categories, body.pay_min, body.metro_ids, has_point,
        body.lng or 0.0, body.lat or 0.0, body.radius_km if has_point else None, body.today_only,
    )
    return sub_out(row)


@app.delete("/api/subscriptions/{sub_id}", status_code=204)
async def delete_subscription(request: Request, sub_id: int, user: User):
    await pool(request).execute("DELETE FROM subscriptions WHERE id = $1 AND user_id = $2", sub_id, user.id)
    return Response(status_code=204)


# --- Mini App -----------------------------------------------------------

if (STATIC_DIR / "index.html").exists():
    if (STATIC_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        file = (STATIC_DIR / path).resolve()
        if path and file.is_file() and STATIC_DIR.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")
