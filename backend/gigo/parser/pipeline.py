"""Обработчик: сырое сообщение → заказы в таблице jobs.

Шаг 1. Отсев флуда правилами (без ИИ).
Шаг 2. Точный повтор уже известного объявления: просто приклеиваем к заказу.
Шаг 3. Разбор ИИ в карточки.
Шаг 4. Метро и адрес → точка, ₽/час, срок жизни, склейка дублей по телефону.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from gigo.parser import rules
from gigo.parser.geo import Geocoder, MetroIndex
from gigo.parser.llm import ParsedJob, ParseError

log = logging.getLogger("gigo.parser")

MAX_ATTEMPTS = 3
DEDUP_WINDOW = timedelta(days=3)


@dataclass
class JobRow:
    category: str
    title: str
    workers_needed: int | None
    pay_amount: float | None
    pay_unit: str | None
    pay_per_hour: float | None
    pay_estimated: bool
    pay_total: float | None
    pay_timing: str | None
    starts_on: object
    starts_at: datetime | None
    duration_hours: float | None
    metro_id: str | None
    address: str | None
    lat: float | None
    lng: float | None
    description: str
    phone: str | None
    scam_flags: list[str]
    hidden: bool
    text_hash: str
    first_seen_at: datetime
    expires_at: datetime


def build_job(job: ParsedJob, text: str, sent_at: datetime, flags: list[str], metro: MetroIndex,
              point: tuple[float, float] | None, h: str) -> JobRow:
    station = next((st for name in job.metro if (st := metro.find(name))), None)
    if point is None and station:
        point = (station.lat, station.lng)
    per_hour, estimated = rules.pay_per_hour(job.pay_amount, job.pay_unit, job.duration_hours)
    start = rules.starts_at(job.date, job.start_time)
    phone = rules.normalize_phone(job.phone) or rules.extract_phone(text)
    return JobRow(
        category=job.category,
        title=job.title,
        workers_needed=job.workers_needed,
        pay_amount=job.pay_amount,
        pay_unit=job.pay_unit,
        pay_per_hour=per_hour,
        pay_estimated=estimated,
        pay_total=rules.pay_total(job.pay_amount, job.pay_unit, job.duration_hours),
        pay_timing=job.pay_timing,
        starts_on=job.date,
        starts_at=start,
        duration_hours=job.duration_hours,
        metro_id=station.id if station else None,
        address=job.address,
        lat=point[0] if point else None,
        lng=point[1] if point else None,
        description=job.description,
        phone=phone,
        scam_flags=flags,
        hidden=bool(flags),
        text_hash=h,
        first_seen_at=sent_at,
        expires_at=rules.expires_at(sent_at, job.date, start, job.duration_hours, job.pay_unit),
    )


_INSERT_JOB = """
INSERT INTO jobs (category, title, workers_needed, pay_amount, pay_unit, pay_per_hour, pay_estimated, pay_total,
                  pay_timing, starts_on, starts_at, duration_hours, metro_id, address, location, description, phone,
                  scam_flags, hidden, text_hash, first_seen_at, last_seen_at, expires_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
        CASE WHEN $15::float8 IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint($16, $15), 4326)::geography END,
        $17, $18, $19, $20, $21, $22, $22, $23)
RETURNING id
"""


class Processor:
    def __init__(self, pool, llm, metro: MetroIndex, geocoder: Geocoder):
        self.pool = pool
        self.llm = llm
        self.metro = metro
        self.geocoder = geocoder

    async def _mark(self, conn, msg_id: int, status: str) -> None:
        await conn.execute(
            "UPDATE raw_messages SET processed_at = now(), parse_status = $2 WHERE id = $1", msg_id, status
        )

    async def _forget_previous(self, conn, msg_id: int) -> None:
        """Сообщение отредактировали: убираем заказы, которые держались только на нём."""
        await conn.execute(
            """DELETE FROM jobs WHERE id IN (
                   SELECT job_id FROM job_messages WHERE raw_message_id = $1
                   EXCEPT SELECT job_id FROM job_messages WHERE raw_message_id <> $1)""",
            msg_id,
        )
        await conn.execute("DELETE FROM job_messages WHERE raw_message_id = $1", msg_id)

    async def _link(self, conn, job_id: int, msg_id: int, sent_at: datetime) -> None:
        await conn.execute(
            "INSERT INTO job_messages (job_id, raw_message_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", job_id, msg_id
        )
        await conn.execute("UPDATE jobs SET last_seen_at = greatest(last_seen_at, $2) WHERE id = $1", job_id, sent_at)

    async def process(self, msg) -> str:
        """Разбирает одно сообщение (запись raw_messages), возвращает итоговый статус."""
        text, sent_at, msg_id = msg["text"], msg["sent_at"], msg["id"]
        async with self.pool.acquire() as conn:
            await self._forget_previous(conn, msg_id)

            if not rules.looks_like_job(text):
                await self._mark(conn, msg_id, "not_job")
                return "not_job"

            h = rules.text_hash(text)
            same = await conn.fetch(
                "SELECT id FROM jobs WHERE text_hash = $1 AND first_seen_at > $2", h, sent_at - DEDUP_WINDOW
            )
            if same:
                for row in same:
                    await self._link(conn, row["id"], msg_id, sent_at)
                await self._mark(conn, msg_id, "duplicate")
                return "duplicate"

        try:
            result = await self.llm.parse(text, sent_at.astimezone(rules.MSK))
        except ParseError as e:
            attempts = await self.pool.fetchval(
                "UPDATE raw_messages SET parse_attempts = parse_attempts + 1 WHERE id = $1 RETURNING parse_attempts",
                msg_id,
            )
            if attempts >= MAX_ATTEMPTS:
                await self._mark(self.pool, msg_id, "error")
            raise e

        if result.kind != "job":
            await self._mark(self.pool, msg_id, result.kind)
            return result.kind

        flags = sorted(set(rules.scam_flags(text)) | set(result.scam_flags))
        rows = []
        for job in result.jobs:
            point = await self.geocoder.locate(job.address) if job.address else None
            rows.append(build_job(job, text, sent_at, flags, self.metro, point, h))

        async with self.pool.acquire() as conn, conn.transaction():
            status = "job"
            for row in rows:
                existing = None
                if row.phone:
                    existing = await conn.fetchval(
                        """SELECT id FROM jobs WHERE phone = $1 AND category = $2
                               AND starts_on IS NOT DISTINCT FROM $3 AND first_seen_at > $4
                           ORDER BY first_seen_at LIMIT 1""",
                        row.phone, row.category, row.starts_on, sent_at - DEDUP_WINDOW,
                    )
                if existing:
                    await self._link(conn, existing, msg_id, sent_at)
                    status = "duplicate"
                    continue
                job_id = await conn.fetchval(
                    _INSERT_JOB,
                    row.category, row.title, row.workers_needed, row.pay_amount, row.pay_unit, row.pay_per_hour,
                    row.pay_estimated, row.pay_total, row.pay_timing, row.starts_on, row.starts_at,
                    row.duration_hours, row.metro_id, row.address, row.lat, row.lng, row.description, row.phone,
                    row.scam_flags, row.hidden, row.text_hash, row.first_seen_at, row.expires_at,
                )
                await self._link(conn, job_id, msg_id, sent_at)
                status = "job"
            await self._mark(conn, msg_id, status)
        return status


async def pending(pool, limit: int, max_age: timedelta) -> list:
    """Неразобранные сообщения, свежие первыми: старьё разбирать незачем, оно уже просрочено."""
    return await pool.fetch(
        """SELECT id, text, sent_at FROM raw_messages
           WHERE processed_at IS NULL AND sent_at > $2
           ORDER BY sent_at DESC LIMIT $1""",
        limit, datetime.now(timezone.utc) - max_age,
    )
