-- Приглашения: заказчик зовёт исполнителя из каталога на свою заявку. Одно приглашение на пару заявка-исполнитель.
CREATE TABLE invites (
    job_id      BIGINT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    worker_id   BIGINT NOT NULL REFERENCES users (tg_id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, worker_id)
);
CREATE INDEX invites_worker ON invites (worker_id);
