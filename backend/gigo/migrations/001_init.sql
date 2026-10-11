-- Gigo: биржа подработки. Заказчики создают заявки, исполнители откликаются.
-- Применяется командой python -m gigo.migrate.

CREATE EXTENSION IF NOT EXISTS postgis;

-- Пользователи Mini App. Роль выбирается при первом входе и меняется в профиле.
CREATE TABLE users (
    tg_id         BIGINT PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    role          TEXT CHECK (role IN ('employer', 'worker')),   -- NULL, пока не выбрал
    about         TEXT,
    bot_blocked   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Станции метро с координатами (справочник hh.ru).
CREATE TABLE metro_stations (
    id         TEXT PRIMARY KEY,                 -- id из hh.ru, например '7.1'
    city       TEXT NOT NULL,
    line       TEXT NOT NULL,
    line_color TEXT,
    name       TEXT NOT NULL,
    location   GEOGRAPHY(Point, 4326) NOT NULL
);
CREATE INDEX metro_stations_name ON metro_stations (lower(name));

-- Заявки заказчиков.
CREATE TABLE jobs (
    id              BIGSERIAL PRIMARY KEY,
    employer_id     BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'closed', 'cancelled')),  -- closed: набрали людей или работа сделана
    city            TEXT NOT NULL DEFAULT 'moscow',
    category        TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    workers_needed  INT NOT NULL DEFAULT 1,
    pay_amount      NUMERIC NOT NULL,
    pay_unit        TEXT NOT NULL,               -- hour | shift | day | task
    pay_per_hour    NUMERIC,                     -- приведено к ₽/час
    pay_estimated   BOOLEAN NOT NULL DEFAULT FALSE,
    pay_total       NUMERIC,
    pay_timing      TEXT,                        -- сразу, в конце смены, ...
    starts_on       DATE,
    starts_at       TIMESTAMPTZ,
    duration_hours  NUMERIC,
    metro_id        TEXT REFERENCES metro_stations (id),
    address         TEXT,
    location        GEOGRAPHY(Point, 4326),
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX jobs_location ON jobs USING GIST (location);
CREATE INDEX jobs_open ON jobs (expires_at) WHERE status = 'open';
CREATE INDEX jobs_employer ON jobs (employer_id, created_at DESC);

-- Отклики исполнителей.
CREATE TABLE responses (
    id          BIGSERIAL PRIMARY KEY,
    job_id      BIGINT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    worker_id   BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    message     TEXT,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'accepted', 'rejected', 'withdrawn')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, worker_id)
);
CREATE INDEX responses_worker ON responses (worker_id, created_at DESC);

-- Отзывы: оставляются только между заказчиком и принятым исполнителем одной заявки.
CREATE TABLE reviews (
    id          BIGSERIAL PRIMARY KEY,
    job_id      BIGINT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    author_id   BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    target_id   BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    rating      INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    text        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, author_id, target_id)
);
CREATE INDEX reviews_target ON reviews (target_id, created_at DESC);

-- Подписки исполнителей: «присылай новые заявки под этот фильтр».
CREATE TABLE subscriptions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    categories  TEXT[] NOT NULL DEFAULT '{}',
    pay_min     NUMERIC,
    metro_ids   TEXT[] NOT NULL DEFAULT '{}',
    location    GEOGRAPHY(Point, 4326),
    radius_km   NUMERIC,
    today_only  BOOLEAN NOT NULL DEFAULT FALSE,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX subscriptions_user ON subscriptions (user_id);

-- Уже отправленные уведомления о новых заявках по подпискам: одна заявка одному человеку один раз.
CREATE TABLE notifications (
    user_id          BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    job_id           BIGINT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    subscription_id  BIGINT REFERENCES subscriptions (id) ON DELETE SET NULL,
    sent_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, job_id)
);

-- Очередь сообщений бота о событиях (новый отклик, отклик принят, ...). API пишет, бот отправляет.
CREATE TABLE outbox (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    text        TEXT NOT NULL,                  -- HTML
    button_text TEXT,
    button_path TEXT,                           -- что открыть в Mini App, например ?job=42
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at     TIMESTAMPTZ,
    attempts    INT NOT NULL DEFAULT 0
);
CREATE INDEX outbox_pending ON outbox (id) WHERE sent_at IS NULL;

-- Кэш геокодера: один адрес не запрашиваем дважды.
CREATE TABLE geocode_cache (
    query       TEXT PRIMARY KEY,
    location    GEOGRAPHY(Point, 4326),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
