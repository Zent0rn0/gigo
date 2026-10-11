"""SQL для заявок и откликов: один источник для ленты, карты, карточки и списков «мои»."""

from dataclasses import dataclass, field


def rating_join(alias: str, user_col: str) -> str:
    """LATERAL с рейтингом пользователя: {alias}.rating, {alias}.reviews_count."""
    return (f"LEFT JOIN LATERAL (SELECT round(avg(rating), 1) AS rating, count(*) AS reviews_count "
            f"FROM reviews WHERE target_id = {user_col}) {alias} ON TRUE")


JOB_FROM = f"""
FROM jobs j
JOIN users e ON e.tg_id = j.employer_id
LEFT JOIN metro_stations m ON m.id = j.metro_id
{rating_join("er", "j.employer_id")}
"""


def job_columns(viewer: str) -> str:
    """Колонки Job; viewer: плейсхолдер с id смотрящего."""
    return f"""
    j.id, j.employer_id, j.status, j.category, j.title, j.description, j.workers_needed,
    j.pay_amount, j.pay_unit, j.pay_per_hour, j.pay_estimated, j.pay_total, j.pay_timing,
    j.starts_on, j.starts_at, j.duration_hours, j.address, j.created_at, j.expires_at, j.hidden_at,
    ST_Y(j.location::geometry) AS lat, ST_X(j.location::geometry) AS lng,
    m.id AS metro_id, m.name AS metro_name, m.line AS metro_line, m.line_color AS metro_color,
    e.first_name AS employer_name, er.rating AS employer_rating, er.reviews_count AS employer_reviews,
    (SELECT count(*) FILTER (WHERE r.status IN ('pending', 'accepted')) FROM responses r WHERE r.job_id = j.id)
        AS responses_count,
    (SELECT count(*) FILTER (WHERE r.status = 'accepted') FROM responses r WHERE r.job_id = j.id) AS accepted_count,
    (SELECT count(*) FILTER (WHERE r.status = 'pending') FROM responses r WHERE r.job_id = j.id) AS pending_count,
    j.employer_id = {viewer} AS is_mine
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


def build_feed(f: JobFilter, viewer_id: int) -> tuple[str, str, list]:
    """Лента открытых заявок: (SQL списка, SQL количества, параметры)."""
    params: list = []

    def p(value) -> str:
        params.append(value)
        return f"${len(params)}"

    viewer = p(viewer_id)
    where = ["j.status = 'open'", "j.expires_at > now()", "j.hidden_at IS NULL", f"{viewer}::bigint IS NOT NULL"]
    if f.categories:
        where.append(f"j.category = ANY({p(f.categories)}::text[])")
    if f.pay_min:
        where.append(f"j.pay_per_hour >= {p(f.pay_min)}")
    if f.metro_ids:
        where.append(f"j.metro_id = ANY({p(f.metro_ids)}::text[])")
    if f.today:
        where.append("(j.starts_on = (now() AT TIME ZONE 'Europe/Moscow')::date "
                     "OR (j.starts_on IS NULL AND j.created_at > now() - interval '12 hours'))")
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
        "distance": "distance_km NULLS LAST, j.created_at DESC" if has_point else "j.created_at DESC",
        "pay": "j.pay_per_hour DESC NULLS LAST, j.created_at DESC",
    }.get(f.sort, "j.created_at DESC")

    base = f"{JOB_FROM} WHERE {' AND '.join(where)}"
    count_sql = f"SELECT count(*) {base}"
    list_sql = (f"SELECT {job_columns(viewer)}, {distance} AS distance_km {base} "
                f"ORDER BY {order}, j.id DESC LIMIT {int(f.limit)} OFFSET {int(f.offset)}")
    return list_sql, count_sql, params


def jobs_where(where: str, order: str = "j.created_at DESC") -> str:
    """Заявки по условию; $1: id смотрящего, дальше параметры условия."""
    return f"SELECT {job_columns('$1')}, NULL::float8 AS distance_km {JOB_FROM} WHERE {where} ORDER BY {order}, j.id DESC"


def responses_where(where: str, order: str = "r.created_at DESC") -> str:
    """Отклики по условию; $1: id смотрящего (для контакта и его отзыва), дальше параметры условия."""
    return f"""
    SELECT r.id, r.job_id, r.status, r.message, r.created_at, r.worker_id, j.employer_id,
           w.first_name AS worker_name, w.username AS worker_username, w.about AS worker_about,
           wr.rating AS worker_rating, wr.reviews_count AS worker_reviews,
           e.first_name AS employer_name, e.username AS employer_username,
           rv.rating AS my_rating, rv.text AS my_text
    FROM responses r
    JOIN jobs j ON j.id = r.job_id
    JOIN users w ON w.tg_id = r.worker_id
    JOIN users e ON e.tg_id = j.employer_id
    {rating_join("wr", "r.worker_id")}
    LEFT JOIN reviews rv ON rv.job_id = r.job_id AND rv.author_id = $1
         AND rv.target_id = CASE WHEN j.employer_id = $1 THEN r.worker_id ELSE j.employer_id END
    WHERE {where}
    ORDER BY {order}, r.id DESC
    """
