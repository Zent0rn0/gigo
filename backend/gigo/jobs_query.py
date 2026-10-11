"""Выборка заказов для API и бота: один SQL на ленту, карту и карточку."""

from dataclasses import dataclass, field

JOB_COLUMNS = """
    j.id, j.category, j.title, j.workers_needed, j.pay_amount, j.pay_unit, j.pay_per_hour, j.pay_estimated,
    j.pay_total, j.pay_timing, j.starts_on, j.starts_at, j.duration_hours, j.address, j.description, j.phone,
    j.first_seen_at, j.expires_at,
    ST_Y(j.location::geometry) AS lat, ST_X(j.location::geometry) AS lng,
    m.id AS metro_id, m.name AS metro_name, m.line AS metro_line, m.line_color AS metro_color,
    (SELECT coalesce(json_agg(json_build_object(
                 'link', r.link, 'chat', coalesce(s.title, s.username), 'sent_at', r.sent_at)
             ORDER BY r.sent_at), '[]')
     FROM job_messages jm JOIN raw_messages r ON r.id = jm.raw_message_id
     LEFT JOIN sources s ON s.chat_id = r.chat_id
     WHERE jm.job_id = j.id AND r.link IS NOT NULL) AS posts
"""


@dataclass
class JobFilter:
    categories: list[str] = field(default_factory=list)
    pay_min: float | None = None
    metro_ids: list[str] = field(default_factory=list)
    today: bool = False
    lat: float | None = None
    lng: float | None = None
    radius_km: float | None = None
    with_location: bool = False
    sort: str = "fresh"
    limit: int = 30
    offset: int = 0


def build(f: JobFilter, job_id: int | None = None) -> tuple[str, str, list]:
    """Возвращает (SQL списка, SQL количества, параметры)."""
    params: list = []

    def p(value) -> str:
        params.append(value)
        return f"${len(params)}"

    where = ["j.expires_at > now()", "NOT j.hidden"]
    if job_id is not None:
        where = [f"j.id = {p(job_id)}"]
    if f.categories:
        where.append(f"j.category = ANY({p(f.categories)}::text[])")
    if f.pay_min:
        where.append(f"j.pay_per_hour >= {p(f.pay_min)}")
    if f.metro_ids:
        where.append(f"j.metro_id = ANY({p(f.metro_ids)}::text[])")
    if f.today:
        where.append("(j.starts_on = (now() AT TIME ZONE 'Europe/Moscow')::date "
                     "OR (j.starts_on IS NULL AND j.first_seen_at > now() - interval '12 hours'))")
    if f.with_location:
        where.append("j.location IS NOT NULL")

    distance = "NULL::float8"
    has_point = f.lat is not None and f.lng is not None
    if has_point:
        point = f"ST_SetSRID(ST_MakePoint({p(f.lng)}, {p(f.lat)}), 4326)::geography"
        distance = f"ST_Distance(j.location, {point}) / 1000"
        if f.radius_km:
            where.append(f"ST_DWithin(j.location, {point}, {p(f.radius_km * 1000)})")
        else:
            where.append(f"{point} IS NOT NULL")  # чтобы запрос количества получал те же параметры

    order = {
        "distance": "distance_km NULLS LAST, j.first_seen_at DESC" if has_point else "j.last_seen_at DESC",
        "pay": "j.pay_per_hour DESC NULLS LAST, j.last_seen_at DESC",
    }.get(f.sort, "j.last_seen_at DESC")

    base = f"FROM jobs j LEFT JOIN metro_stations m ON m.id = j.metro_id WHERE {' AND '.join(where)}"
    count_sql = f"SELECT count(*) {base}"
    list_sql = (f"SELECT {JOB_COLUMNS}, {distance} AS distance_km {base} "
                f"ORDER BY {order}, j.id DESC LIMIT {int(f.limit)} OFFSET {int(f.offset)}")
    return list_sql, count_sql, params
