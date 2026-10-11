# API Gigo

Базовый путь `/api`. Ответы в JSON. Даты в ISO 8601 с часовым поясом.

## Вход

Каждый запрос из Mini App несёт заголовок

    Authorization: tma <Telegram.WebApp.initData>

Сервер проверяет подпись initData токеном бота. Без заголовка или с плохой подписью: `401`.
При `DEV_AUTH=1` на сервере заголовок необязателен (пользователь id 1, для разработки в браузере).

## GET /api/meta

Справочники для фильтров.

```json
{
  "categories": [{"id": "loader", "label": "Грузчики", "emoji": "📦"}, ...],
  "metro": [{"id": "7.1", "name": "Таганская", "line": "Таганско-Краснопресненская", "color": "#943E90", "lat": 55.73, "lng": 37.65}, ...],
  "city": {"id": "moscow", "name": "Москва", "lat": 55.7558, "lng": 37.6176}
}
```

Категории: `loader` Грузчики, `courier` Курьеры, `warehouse` Склад, `cleaning` Уборка,
`construction` Стройка, `promo` Промоутеры, `kitchen` Общепит, `driver` Водители, `event` Мероприятия, `other` Другое.

## GET /api/jobs

Активные заказы (не просроченные и не скрытые).

Параметры (все необязательные):

| Параметр | Пример | Смысл |
|---|---|---|
| `category` | `category=loader&category=courier` | одна или несколько категорий |
| `pay_min` | `400` | ₽/час от |
| `metro` | `metro=7.1&metro=1.5` | станции метро |
| `today` | `true` | только на сегодня |
| `lat`, `lng` | `55.73`, `37.65` | где пользователь: включает `distance_km` в ответе |
| `radius_km` | `5` | только в радиусе (нужны `lat`, `lng`) |
| `sort` | `fresh` \| `distance` \| `pay` | по умолчанию `fresh`; `distance` нужны `lat`, `lng` |
| `with_location` | `true` | только заказы с точкой на карте (для карты) |
| `limit`, `offset` | `30`, `0` | страница; `limit` до 500 |

```json
{
  "total": 124,
  "items": [Job, ...]
}
```

### Job

```json
{
  "id": 42,
  "category": "loader",
  "title": "Грузчики ×2 · переезд офиса",
  "workers_needed": 2,
  "pay_amount": 500, "pay_unit": "hour",
  "pay_per_hour": 500, "pay_estimated": false,
  "pay_total": 2000,
  "pay_timing": "сразу",
  "starts_on": "2026-10-11",
  "starts_at": "2026-10-11T14:00:00+03:00",
  "duration_hours": 4,
  "metro": {"id": "7.1", "name": "Таганская", "line": "Таганско-Краснопресненская", "color": "#943E90"},
  "address": null,
  "lat": 55.7393, "lng": 37.6533,
  "distance_km": 1.8,
  "description": "Переезд офиса, нужны 2 человека на ~4 часа.",
  "phone": "79001234567",
  "posts": [{"link": "https://t.me/gruzchiki_msk/123", "chat": "Грузчики Москва", "sent_at": "2026-10-11T13:02:00+03:00"}],
  "first_seen_at": "2026-10-11T13:02:00+03:00",
  "expires_at": "2026-10-11T15:00:00+03:00"
}
```

Любое поле, кроме `id`, `category`, `title`, `posts`, `first_seen_at`, `expires_at`, может быть `null`.
`pay_unit`: `hour` | `shift` | `day` | `task` | `month`.

## GET /api/jobs/{id}

Один `Job`. `404`, если не найден.

## Подписки

### GET /api/subscriptions

```json
[{"id": 1, "name": "Грузчики от 500 ₽/ч", "categories": ["loader"], "pay_min": 500,
  "metro_ids": [], "lat": null, "lng": null, "radius_km": null, "today_only": false, "enabled": true}]
```

### POST /api/subscriptions

Тело как элемент выше, без `id` и `enabled`. Обязательно только `name`. Ответ: созданная подписка. Не больше 10 подписок на человека (`409`).

### DELETE /api/subscriptions/{id}

`204`.

## GET /api/health

`{"ok": true}`
