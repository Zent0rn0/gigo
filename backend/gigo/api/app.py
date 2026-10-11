"""HTTP API для Mini App. Контракт: docs/api.md.

    uvicorn gigo.api.app:app --port 8000
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from gigo import config, db
from gigo.api.auth import InitDataError, TgUser, validate_init_data
from gigo.categories import CATEGORIES
from gigo.jobs_query import JobFilter, build
from gigo.migrate import migrate

log = logging.getLogger("gigo.api")

CITY = {"id": "moscow", "name": "Москва", "lat": 55.7558, "lng": 37.6176}
MAX_SUBSCRIPTIONS = 10
STATIC_DIR = Path(os.getenv("STATIC_DIR", config.ROOT / "frontend" / "dist"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = config.load()
    await migrate(settings.database_url)
    app.state.settings = settings
    app.state.pool = await db.connect(settings.database_url)
    if not settings.bot_token and not settings.dev_auth:
        log.warning("BOT_TOKEN не задан: вход из Mini App работать не будет")
    yield
    await app.state.pool.close()


app = FastAPI(title="Gigo", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")


# --- вход ---------------------------------------------------------------

async def current_user(request: Request, authorization: Annotated[str | None, Header()] = None) -> TgUser:
    settings: config.Settings = request.app.state.settings
    if authorization and authorization.startswith("tma ") and settings.bot_token:
        try:
            user = validate_init_data(authorization[4:], settings.bot_token)
        except InitDataError as e:
            raise HTTPException(401, f"Вход не подтверждён: {e}")
    elif settings.dev_auth:
        user = TgUser(1, "dev", "Разработчик")
    else:
        raise HTTPException(401, "Откройте приложение из Telegram")
    await request.app.state.pool.execute(
        """INSERT INTO users (tg_id, username, first_name) VALUES ($1, $2, $3)
           ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username, first_name = EXCLUDED.first_name,
               last_seen_at = now(), bot_blocked = FALSE""",
        user.id, user.username, user.first_name,
    )
    return user


User = Annotated[TgUser, Depends(current_user)]


# --- заказы -------------------------------------------------------------

def _num(v):
    return float(v) if v is not None else None


def job_out(r) -> dict:
    return {
        "id": r["id"],
        "category": r["category"],
        "title": r["title"],
        "workers_needed": r["workers_needed"],
        "pay_amount": _num(r["pay_amount"]),
        "pay_unit": r["pay_unit"],
        "pay_per_hour": _num(r["pay_per_hour"]),
        "pay_estimated": r["pay_estimated"],
        "pay_total": _num(r["pay_total"]),
        "pay_timing": r["pay_timing"],
        "starts_on": r["starts_on"].isoformat() if r["starts_on"] else None,
        "starts_at": r["starts_at"].isoformat() if r["starts_at"] else None,
        "duration_hours": _num(r["duration_hours"]),
        "metro": {"id": r["metro_id"], "name": r["metro_name"], "line": r["metro_line"],
                  "color": f"#{r['metro_color']}" if r["metro_color"] else None} if r["metro_id"] else None,
        "address": r["address"],
        "lat": r["lat"],
        "lng": r["lng"],
        "distance_km": round(r["distance_km"], 1) if r["distance_km"] is not None else None,
        "description": r["description"],
        "phone": r["phone"],
        "posts": json.loads(r["posts"]) if isinstance(r["posts"], str) else r["posts"],
        "first_seen_at": r["first_seen_at"].isoformat(),
        "expires_at": r["expires_at"].isoformat(),
    }


@app.get("/api/health")
async def health(request: Request):
    await request.app.state.pool.fetchval("SELECT 1")
    return {"ok": True}


@app.get("/api/meta")
async def meta(request: Request, _: User):
    rows = await request.app.state.pool.fetch(
        "SELECT id, name, line, line_color, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
        "FROM metro_stations WHERE city = $1 ORDER BY name, id", CITY["id"],
    )
    return {
        "categories": [{"id": k, "label": label, "emoji": emoji} for k, (label, emoji) in CATEGORIES.items()],
        "metro": [{"id": r["id"], "name": r["name"], "line": r["line"],
                   "color": f"#{r['line_color']}" if r["line_color"] else None, "lat": r["lat"], "lng": r["lng"]}
                  for r in rows],
        "city": CITY,
    }


@app.get("/api/jobs")
async def list_jobs(
    request: Request,
    _: User,
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
    list_sql, count_sql, params = build(f)
    pool = request.app.state.pool
    rows = await pool.fetch(list_sql, *params)
    total = await pool.fetchval(count_sql, *params)
    return {"total": total, "items": [job_out(r) for r in rows]}


@app.get("/api/jobs/{job_id}")
async def get_job(request: Request, job_id: int, _: User):
    list_sql, _count, params = build(JobFilter(limit=1), job_id=job_id)
    row = await request.app.state.pool.fetchrow(list_sql, *params)
    if not row:
        raise HTTPException(404, "Заказ не найден")
    return job_out(row)


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
    rows = await request.app.state.pool.fetch(
        f"SELECT {_SUB_COLUMNS} FROM subscriptions WHERE user_id = $1 ORDER BY id", user.id
    )
    return [sub_out(r) for r in rows]


@app.post("/api/subscriptions", status_code=201)
async def create_subscription(request: Request, body: SubscriptionIn, user: User):
    pool = request.app.state.pool
    if await pool.fetchval("SELECT count(*) FROM subscriptions WHERE user_id = $1", user.id) >= MAX_SUBSCRIPTIONS:
        raise HTTPException(409, f"Можно не больше {MAX_SUBSCRIPTIONS} подписок")
    categories = [c for c in body.categories if c in CATEGORIES]
    has_point = body.lat is not None and body.lng is not None
    row = await pool.fetchrow(
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
    await request.app.state.pool.execute("DELETE FROM subscriptions WHERE id = $1 AND user_id = $2", sub_id, user.id)
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
