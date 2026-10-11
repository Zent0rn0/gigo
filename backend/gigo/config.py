"""Настройки из переменных окружения (.env в корне проекта)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def _str(name: str) -> str | None:
    return os.getenv(name, "").strip() or None


@dataclass(frozen=True)
class Settings:
    database_url: str
    tg_api_id: int | None
    tg_api_hash: str | None
    tg_session: str
    data_dir: Path
    sources_file: Path
    backfill_days: int
    join_delay_min: int
    join_delay_max: int
    join_batch: int
    llm_provider: str
    anthropic_api_key: str | None
    claude_model: str
    yandex_api_key: str | None
    yandex_folder_id: str | None
    yandex_gpt_model: str
    yandex_geocoder_key: str | None
    parser_concurrency: int
    bot_token: str | None
    webapp_url: str | None
    dev_auth: bool

    @property
    def session_path(self) -> Path:
        return self.data_dir / self.tg_session

    def require_telegram(self) -> None:
        if not self.tg_api_id or not self.tg_api_hash:
            raise SystemExit(
                "Не заданы TG_API_ID и TG_API_HASH. Получите их на my.telegram.org "
                "с аккаунта-сборщика и впишите в файл .env"
            )


def load() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", ROOT / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    api_id = os.getenv("TG_API_ID", "").strip()
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql://gigo:gigo@localhost:5432/gigo"),
        tg_api_id=int(api_id) if api_id else None,
        tg_api_hash=os.getenv("TG_API_HASH", "").strip() or None,
        tg_session=os.getenv("TG_SESSION", "collector"),
        data_dir=data_dir,
        sources_file=Path(os.getenv("SOURCES_FILE", ROOT / "sources.txt")),
        backfill_days=_int("BACKFILL_DAYS", 7),
        join_delay_min=_int("JOIN_DELAY_MIN", 120),
        join_delay_max=_int("JOIN_DELAY_MAX", 300),
        join_batch=_int("JOIN_BATCH", 5),
        llm_provider=os.getenv("LLM_PROVIDER", "claude").strip().lower(),
        anthropic_api_key=_str("ANTHROPIC_API_KEY"),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-haiku-5-5"),
        yandex_api_key=_str("YANDEX_GPT_API_KEY"),
        yandex_folder_id=_str("YANDEX_FOLDER_ID"),
        yandex_gpt_model=os.getenv("YANDEX_GPT_MODEL", "yandexgpt-lite/latest"),
        yandex_geocoder_key=_str("YANDEX_GEOCODER_KEY"),
        parser_concurrency=_int("PARSER_CONCURRENCY", 4),
        bot_token=_str("BOT_TOKEN"),
        webapp_url=_str("WEBAPP_URL"),
        dev_auth=os.getenv("DEV_AUTH", "").strip() in ("1", "true", "yes"),
    )
