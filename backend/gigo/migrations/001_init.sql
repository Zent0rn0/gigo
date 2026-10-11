-- Gigo: начальная схема. Применяется командой python -m gigo.migrate.

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
    parse_status  TEXT,                          -- job | duplicate | not_job | spam | error
    parse_attempts INT NOT NULL DEFAULT 0,
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

-- Заказы после разбора ИИ.
CREATE TABLE jobs (
    id              BIGSERIAL PRIMARY KEY,
    city            TEXT NOT NULL DEFAULT 'moscow',
    category        TEXT NOT NULL,               -- loader, courier, warehouse, cleaning, construction, promo, kitchen, driver, other
    title           TEXT NOT NULL,
    workers_needed  INT,
    pay_amount      NUMERIC,                     -- как в объявлении
    pay_unit        TEXT,                        -- hour | shift | day | task | month
    pay_per_hour    NUMERIC,                     -- приведено к ₽/час
    pay_estimated   BOOLEAN NOT NULL DEFAULT FALSE, -- ₽/час посчитан с допущением о длине смены
    pay_total       NUMERIC,
    pay_timing      TEXT,                        -- сразу, в конце смены, ...
    starts_on       DATE,                        -- день работы по Москве
    starts_at       TIMESTAMPTZ,                 -- точное время начала, если указано
    duration_hours  NUMERIC,
    metro_id        TEXT REFERENCES metro_stations (id),
    address         TEXT,
    location        GEOGRAPHY(Point, 4326),
    description     TEXT,
    phone           TEXT,                        -- только цифры, 7XXXXXXXXXX
    scam_flags      TEXT[] NOT NULL DEFAULT '{}',
    hidden          BOOLEAN NOT NULL DEFAULT FALSE,
    text_hash       TEXT NOT NULL,               -- для склейки одинаковых репостов
    first_seen_at   TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX jobs_location ON jobs USING GIST (location);
CREATE INDEX jobs_active ON jobs (expires_at) WHERE NOT hidden;
CREATE INDEX jobs_text_hash ON jobs (text_hash);
CREATE INDEX jobs_phone ON jobs (phone) WHERE phone IS NOT NULL;

-- Какие сообщения слились в один заказ (один заказ публикуют в 10 чатах).
CREATE TABLE job_messages (
    job_id          BIGINT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    raw_message_id  BIGINT NOT NULL REFERENCES raw_messages (id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, raw_message_id)
);

-- Пользователи Mini App (заводятся при первом входе).
CREATE TABLE users (
    tg_id         BIGINT PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    bot_blocked   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Подписки: «присылай заказы под этот фильтр».
CREATE TABLE subscriptions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    categories  TEXT[] NOT NULL DEFAULT '{}',   -- пусто = любые
    pay_min     NUMERIC,                        -- ₽/час «от»
    metro_ids   TEXT[] NOT NULL DEFAULT '{}',
    location    GEOGRAPHY(Point, 4326),         -- центр «рядом со мной»
    radius_km   NUMERIC,
    today_only  BOOLEAN NOT NULL DEFAULT FALSE,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX subscriptions_user ON subscriptions (user_id);

-- Что уже отправили: один заказ одному человеку — одно уведомление.
CREATE TABLE notifications (
    user_id          BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    job_id           BIGINT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    subscription_id  BIGINT REFERENCES subscriptions (id) ON DELETE SET NULL,
    sent_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, job_id)
);

-- Кэш геокодера: один адрес не запрашиваем дважды (у Геокодера дневной лимит).
CREATE TABLE geocode_cache (
    query       TEXT PRIMARY KEY,
    location    GEOGRAPHY(Point, 4326),        -- NULL, если адрес не нашёлся
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
