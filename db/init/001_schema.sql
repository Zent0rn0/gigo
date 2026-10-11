-- Gigo: схема базы. Выполняется один раз при первом старте контейнера postgis.

CREATE EXTENSION IF NOT EXISTS postgis;

-- Чаты-источники, которые читает аккаунт-сборщик.
CREATE TABLE sources (
    id           BIGSERIAL PRIMARY KEY,
    link         TEXT NOT NULL UNIQUE,          -- как в sources.txt: t.me/xxx или @xxx
    chat_id      BIGINT UNIQUE,                 -- id чата в Telegram, заполняется после вступления
    username     TEXT,
    title        TEXT,
    city         TEXT NOT NULL DEFAULT 'moscow',
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    joined_at    TIMESTAMPTZ,
    last_error   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Сырые сообщения из чатов, как есть. Парсер (этап 2) берёт отсюда.
CREATE TABLE raw_messages (
    id            BIGSERIAL PRIMARY KEY,
    chat_id       BIGINT NOT NULL,
    message_id    BIGINT NOT NULL,
    sender_id     BIGINT,
    sent_at       TIMESTAMPTZ NOT NULL,
    edited_at     TIMESTAMPTZ,
    text          TEXT NOT NULL,
    link          TEXT,                          -- ссылка на оригинал: t.me/username/123
    collected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ,                   -- когда парсер его разобрал
    parse_status  TEXT,                          -- job | not_job | spam | scam | error
    UNIQUE (chat_id, message_id)
);
CREATE INDEX raw_messages_unprocessed ON raw_messages (sent_at) WHERE processed_at IS NULL;
CREATE INDEX raw_messages_sent_at ON raw_messages (sent_at DESC);

-- Станции метро с координатами (справочник hh.ru).
CREATE TABLE metro_stations (
    id        TEXT PRIMARY KEY,                  -- id из hh.ru, например '1.1'
    city      TEXT NOT NULL,
    line      TEXT NOT NULL,
    line_color TEXT,
    name      TEXT NOT NULL,
    location  GEOGRAPHY(Point, 4326) NOT NULL
);
CREATE INDEX metro_stations_name ON metro_stations (lower(name));

-- Заказы после разбора ИИ. Заполняются на этапе 2.
CREATE TABLE jobs (
    id              BIGSERIAL PRIMARY KEY,
    category        TEXT NOT NULL,               -- loader, courier, cleaner, promo, warehouse, other
    title           TEXT NOT NULL,
    workers_needed  INT,
    pay_amount      NUMERIC,                     -- как в объявлении
    pay_unit        TEXT,                        -- hour | shift | day | task | month
    pay_per_hour    NUMERIC,                     -- приведено к ₽/час, если можно посчитать
    pay_total       NUMERIC,
    pay_timing      TEXT,                        -- сразу, в конце смены, ...
    starts_at       TIMESTAMPTZ,
    duration_hours  NUMERIC,
    metro_id        TEXT REFERENCES metro_stations (id),
    address         TEXT,
    location        GEOGRAPHY(Point, 4326),
    description     TEXT,
    scam_flags      TEXT[] NOT NULL DEFAULT '{}',
    hidden          BOOLEAN NOT NULL DEFAULT FALSE,
    fingerprint     TEXT NOT NULL,               -- для склейки дублей из разных чатов
    first_seen_at   TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX jobs_location ON jobs USING GIST (location);
CREATE INDEX jobs_active ON jobs (expires_at) WHERE NOT hidden;
CREATE INDEX jobs_fingerprint ON jobs (fingerprint);

-- Какие сообщения слились в один заказ (один заказ публикуют в 10 чатах).
CREATE TABLE job_messages (
    job_id          BIGINT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    raw_message_id  BIGINT NOT NULL REFERENCES raw_messages (id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, raw_message_id)
);
