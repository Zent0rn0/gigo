-- Модерация, жалобы и кнопки в сообщениях бота.

-- Блокировка пользователя модератором.
ALTER TABLE users ADD COLUMN banned_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN ban_reason TEXT;

-- Скрытая модератором (или по жалобам) заявка не показывается в ленте и не рассылается по подпискам.
ALTER TABLE jobs ADD COLUMN hidden_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN hidden_reason TEXT;

-- Жалобы на заявки. Один человек — одна жалоба на заявку.
CREATE TABLE reports (
    id           BIGSERIAL PRIMARY KEY,
    job_id       BIGINT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    author_id    BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    reason       TEXT NOT NULL CHECK (reason IN ('scam', 'spam', 'rude', 'other')),
    text         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ,
    UNIQUE (job_id, author_id)
);
CREATE INDEX reports_open ON reports (created_at) WHERE resolved_at IS NULL;

-- Инлайн-кнопки сообщения бота: [[{"text": "Принять", "data": "acc:7"}], [{"text": "Открыть", "path": "?job=42"}]]
ALTER TABLE outbox ADD COLUMN buttons JSONB;

-- Напоминание перед началом работы и просьба оставить отзыв после: каждое один раз.
ALTER TABLE responses ADD COLUMN reminded_at TIMESTAMPTZ;
ALTER TABLE responses ADD COLUMN review_asked_at TIMESTAMPTZ;

-- Для лимитов «не больше N откликов в час».
CREATE INDEX responses_worker_recent ON responses (worker_id, updated_at DESC);

-- Одна кнопка заменена списком кнопок.
ALTER TABLE outbox DROP COLUMN button_text;
ALTER TABLE outbox DROP COLUMN button_path;
