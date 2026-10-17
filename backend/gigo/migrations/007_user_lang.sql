-- Язык интерфейса: ru, en, uz, tg, ky, kk, az, hy. NULL — ещё не выбран (берётся язык Telegram).
ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT;
