"""Адрес → точка на карте через Яндекс Геокодер."""

import logging

import httpx

log = logging.getLogger("gigo.geo")

MOSCOW_BBOX = "36.8,55.1~38.3,56.1"


class Geocoder:
    """Яндекс Геокодер с кэшем в базе. Без ключа ничего не делает."""

    URL = "https://geocode-maps.yandex.ru/1.x/"

    def __init__(self, api_key: str | None, pool, city_name: str = "Москва"):
        self.api_key = api_key
        self.pool = pool
        self.city_name = city_name
        self.http = httpx.AsyncClient(timeout=15) if api_key else None

    async def locate(self, address: str) -> tuple[float, float] | None:
        if not self.http or not address:
            return None
        query = f"{self.city_name}, {address.strip()}"[:300]
        cached = await self.pool.fetchrow(
            "SELECT ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng FROM geocode_cache WHERE query = $1",
            query,
        )
        if cached:
            return (cached["lat"], cached["lng"]) if cached["lat"] is not None else None
        point = await self._request(query)
        await self.pool.execute(
            "INSERT INTO geocode_cache (query, location) VALUES ($1, "
            "CASE WHEN $2::float8 IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography END) "
            "ON CONFLICT (query) DO NOTHING",
            query, point[0] if point else None, point[1] if point else None,
        )
        return point

    async def _request(self, query: str) -> tuple[float, float] | None:
        try:
            resp = await self.http.get(self.URL, params={
                "apikey": self.api_key, "geocode": query, "format": "json", "results": 1,
                "bbox": MOSCOW_BBOX, "rspn": 1, "lang": "ru_RU",
            })
            resp.raise_for_status()
            members = resp.json()["response"]["GeoObjectCollection"]["featureMember"]
        except httpx.HTTPStatusError as e:  # в тексте исключения URL с ключом: в лог его не пишем
            log.warning("геокодер ответил %s", e.response.status_code)
            return None
        except (httpx.HTTPError, KeyError, ValueError) as e:
            log.warning("геокодер: %s", type(e).__name__)
            return None
        if not members:
            return None
        obj = members[0]["GeoObject"]
        precision = obj.get("metaDataProperty", {}).get("GeocoderMetaData", {}).get("precision")
        if precision == "other":  # нашёлся только город целиком: такой точке не верим
            return None
        lng, lat = map(float, obj["Point"]["pos"].split())
        return lat, lng
