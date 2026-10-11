# Gigo · Mini App

Telegram Mini App: лента заказов на подработку, карточка заказа, карта и подписки.
React 18 + TypeScript + Vite, без UI-библиотек; цвета берутся из темы Telegram (`--tg-theme-*`), в обычном браузере работают светлая и тёмная темы.

Контракт API: [`../docs/api.md`](../docs/api.md).

## Команды

Нужен Node.js 20+.

```bash
cd frontend
npm install

npm run dev          # http://localhost:5173, /api проксируется на http://localhost:8000
npm run dev:mock     # то же, но без бэкенда: тестовые заказы из src/mock/fixture.ts
npm run build        # tsc --noEmit + сборка в dist/
npm run build:mock   # сборка с тестовыми данными (для демо)
npm run preview      # раздать dist/ на http://localhost:4173 (с тем же прокси /api)
npm run typecheck
```

Для разработки в браузере без Telegram запустите бэкенд с `DEV_AUTH=1`: заголовок
`Authorization: tma <initData>` отправляется только внутри Telegram.

## Переменные окружения

Кладите в `frontend/.env.local` (не коммитится), образец в `.env.example`.

| Переменная | Зачем |
|---|---|
| `VITE_YANDEX_MAPS_KEY` | ключ JavaScript API Яндекс Карт 2.1. Без него вкладка «Карта» показывает заглушку |
| `VITE_MOCK` | `1` — работать на тестовых данных без бэкенда (то же делает `--mode mock`, см. `.env.mock`) |

## Как устроено

- `src/api.ts` — типизированный клиент (`/api/meta`, `/api/jobs`, `/api/jobs/{id}`, `/api/subscriptions`), типы в `src/types.ts`.
- `src/telegram.ts` — `Telegram.WebApp`: `ready()`, `expand()`, BackButton, открытие ссылок, deep link.
- `src/screens/` — Лента, Карточка заказа, Карта, Подписки; навигация — состояние в `App.tsx`.
- `src/filters.ts` — фильтры ленты (запоминаются в `localStorage`), запрос к API, имя подписки.
- `src/mock/` — фикстура и имитация API для `VITE_MOCK=1`.

Ссылка прямо на заказ: `https://<домен>/?job=42` или `https://t.me/<бот>/<app>?startapp=job_42`.

## Скриншоты

`screenshots/` — лента, карточка и подписки в режиме mock (Chromium, 390×844).
