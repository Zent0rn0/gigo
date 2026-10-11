-- Избранные заявки: исполнитель сохраняет, чтобы вернуться позже.
CREATE TABLE saved_jobs (
    user_id     BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    job_id      BIGINT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, job_id)
);
CREATE INDEX saved_jobs_job ON saved_jobs (job_id);
