"""Загрузка станций метро с координатами из бесплатного справочника hh.ru.

    python -m gigo.metro            # Москва
    python -m gigo.metro --city 2   # Санкт-Петербург (id города в hh.ru)
"""

import argparse
import asyncio

import httpx

from gigo import config, db

HH_CITIES = {"1": "moscow", "2": "spb"}


def parse_metro(data: dict, city: str) -> list[tuple]:
    rows = []
    for line in data["lines"]:
        for st in line["stations"]:
            if st.get("lat") is None or st.get("lng") is None:
                continue
            rows.append((st["id"], city, line["name"], line.get("hex_color"), st["name"], st["lng"], st["lat"]))
    return rows


async def load(city_id: str) -> None:
    settings = config.load()
    city = HH_CITIES.get(city_id, city_id)
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "gigo/0.1"}) as http:
        resp = await http.get(f"https://api.hh.ru/metro/{city_id}")
        resp.raise_for_status()
    rows = parse_metro(resp.json(), city)
    pool = await db.connect(settings.database_url)
    await pool.executemany(
        """INSERT INTO metro_stations (id, city, line, line_color, name, location)
           VALUES ($1, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($6, $7), 4326)::geography)
           ON CONFLICT (id) DO UPDATE SET line = EXCLUDED.line, line_color = EXCLUDED.line_color,
               name = EXCLUDED.name, location = EXCLUDED.location""",
        rows,
    )
    await pool.close()
    print(f"Загружено станций: {len(rows)} ({city})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m gigo.metro")
    parser.add_argument("--city", default="1", help="id города в hh.ru: 1 Москва, 2 Петербург")
    asyncio.run(load(parser.parse_args().city))


if __name__ == "__main__":
    main()
