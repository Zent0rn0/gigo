# Баннеры бота

PNG 1280×640, по одному на раздел: `welcome`, `find`, `near`, `new`, `published`, `my`, `responses`,
`subs`, `accepted`, `review`, `help`. Если файла нет, бот отправляет сообщение без картинки.

Исходник — `docs/brand/banners/banner.html` (подписи и иконки в объекте `BANNERS`).
Пересобрать: `node scripts/render_banners.mjs` (нужен Playwright с Chromium).
