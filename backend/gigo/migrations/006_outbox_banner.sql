-- Картинка-баннер над сообщением из очереди (имя файла в gigo/bot/banners без расширения).
ALTER TABLE outbox ADD COLUMN IF NOT EXISTS banner TEXT;
