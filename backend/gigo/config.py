"""Настройки из переменных окружения (.env в корне проекта)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _str(name: str) -> str | None:
    return os.getenv(name, "").strip() or None


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    yandex_geocoder_key: str | None
    bot_token: str | None
    webapp_url: str | None
    dev_auth: bool
    admin_ids: tuple[int, ...]


def load() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", ROOT / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql://gigo:gigo@localhost:5432/gigo"),
        data_dir=data_dir,
        yandex_geocoder_key=_str("YANDEX_GEOCODER_KEY"),
        bot_token=_str("BOT_TOKEN"),
        webapp_url=_str("WEBAPP_URL"),
        dev_auth=os.getenv("DEV_AUTH", "").strip() in ("1", "true", "yes"),
        admin_ids=tuple(int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()),
    )
