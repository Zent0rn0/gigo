"""Метро и адрес → точка на карте."""

import logging
import re
from dataclasses import dataclass

import httpx

log = logging.getLogger("gigo.parser.geo")


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    lat: float
    lng: float


def _norm(name: str) -> str:
    s = name.lower().replace("ё", "е")
    s = re.sub(r"\b(?:м|ст|метро|станция|мцк|мцд(?:-?\d)?)\b\.?", " ", s)
    s = re.sub(r"[^0-9a-zа-я]+", " ", s)
    return " ".join(s.split())


# Окончания падежей: «на Таганской», «у Пушкинской», «от Курской».
_ENDINGS = ("ской", "ская", "ую", "ой", "ая", "ий", "ей", "ом", "ем", "ые", "ых", "а", "е", "и", "у", "ы", "о")


def _stem(word: str) -> str:
    for end in _ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 3:
            return word[: -len(end)]
    return word


def _stem_phrase(name: str) -> str:
    return " ".join(_stem(w) for w in name.split())


class MetroIndex:
    def __init__(self, stations: list[Station]):
        self.exact: dict[str, Station] = {}
        self.stems: dict[str, Station] = {}
        for st in stations:
            key = _norm(st.name)
            self.exact.setdefault(key, st)
            self.stems.setdefault(_stem_phrase(key), st)

    def find(self, raw: str) -> Station | None:
        key = _norm(raw)
        if not key:
            return None
        if st := self.exact.get(key):
            return st
        return self.stems.get(_stem_phrase(key))

    @classmethod
    async def load(cls, pool, city: str) -> "MetroIndex":
        rows = await pool.fetch(
            "SELECT id, name, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
            "FROM metro_stations WHERE city = $1 ORDER BY id",
            city,
        )
        return cls([Station(r["id"], r["name"], r["lat"], r["lng"]) for r in rows])


# Москва с запасом: адреса за её пределами не принимаем.
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
        except (httpx.HTTPError, KeyError, ValueError) as e:
            log.warning("геокодер: %s", e)
            return None
        if not members:
            return None
        obj = members[0]["GeoObject"]
        precision = obj.get("metaDataProperty", {}).get("GeocoderMetaData", {}).get("precision")
        if precision == "other":  # нашёлся только город целиком: такой точке не верим
            return None
        lng, lat = map(float, obj["Point"]["pos"].split())
        return lat, lng
