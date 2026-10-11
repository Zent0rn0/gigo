"""Разбор текста объявления моделью: Claude или YandexGPT, ответ строго по JSON-схеме."""

import json
import logging
from dataclasses import dataclass, field
import datetime as dt
from datetime import date, datetime, time

import httpx

from gigo.categories import CATEGORIES, PAY_UNITS, SCAM_FLAGS

log = logging.getLogger("gigo.parser.llm")


def _nullable(t: str, **extra) -> dict:
    return {"anyOf": [{"type": t, **extra}, {"type": "null"}]}


JOB_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "title": {"type": "string"},
        "workers_needed": _nullable("integer"),
        "pay_amount": _nullable("number"),
        "pay_unit": _nullable("string", enum=list(PAY_UNITS)),
        "pay_timing": _nullable("string"),
        "date": _nullable("string"),
        "start_time": _nullable("string"),
        "duration_hours": _nullable("number"),
        "metro": {"type": "array", "items": {"type": "string"}},
        "address": _nullable("string"),
        "phone": _nullable("string"),
        "description": {"type": "string"},
    },
    "required": ["category", "title", "workers_needed", "pay_amount", "pay_unit", "pay_timing", "date",
                 "start_time", "duration_hours", "metro", "address", "phone", "description"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["job", "not_job", "spam"]},
        "scam_flags": {"type": "array", "items": {"type": "string", "enum": list(SCAM_FLAGS)}},
        "jobs": {"type": "array", "items": JOB_SCHEMA},
    },
    "required": ["kind", "scam_flags", "jobs"],
    "additionalProperties": False,
}

_categories = "\n".join(f"- {k}: {label}" for k, (label, _) in CATEGORIES.items())
_flags = "\n".join(f"- {k}: {v}" for k, v in SCAM_FLAGS.items())

SYSTEM_PROMPT = f"""Ты разбираешь сообщения из Telegram-чатов с подработкой в Москве и превращаешь их в карточки заказов для приложения, где люди ищут работу.

Определи kind:
- job: кто-то ищет работников (разовая подработка, смены, вакансия).
- not_job: разговоры, вопросы, резюме («ищу работу», «готов работать»), отзывы, правила чата.
- spam: реклама услуг и товаров, курсы, каналы, боты, «пиши в лс — расскажу».

Если в одном сообщении несколько разных работ, сделай отдельную карточку на каждую. Для not_job и spam массив jobs пустой.

Категории:
{_categories}

Поля карточки:
- title: коротко, как заголовок в ленте, до 60 символов, без капса и смайлов. Например: «Грузчики ×2 · переезд офиса».
- workers_needed: сколько человек нужно, если сказано.
- pay_amount и pay_unit: сумма в рублях и за что она: hour (за час), shift (за смену), day (за день), task (за всю работу), month (в месяц). «500р/ч» это 500 и hour. «2000 за смену» это 2000 и shift. Если указан диапазон, бери нижнюю границу. Нет оплаты: null.
- pay_timing: когда платят, своими словами коротко («сразу», «в конце смены», «раз в неделю»), иначе null.
- date: день работы в формате YYYY-MM-DD. «сегодня» и «завтра» считай от даты публикации. Не сказано: null.
- start_time: время начала HH:MM, иначе null.
- duration_hours: сколько часов длится работа или смена, если сказано или однозначно следует из «с 9 до 18».
- metro: названия станций метро или МЦК/МЦД, как в тексте, но без «м.» и «ст.». Пусто, если нет.
- address: адрес или ориентир, если есть, иначе null.
- phone: телефон для связи, если есть.
- description: 1–2 предложения: что делать и важные условия (паспорт, медкнижка, гражданство, возраст). Без телефона.

scam_flags: признаки обмана или криминала, даже если kind=job:
{_flags}
Обычные вакансии курьеров, складов и грузчиков с понятной оплатой подозрительными не считай.

Ничего не придумывай: чего нет в тексте, то null."""


@dataclass
class ParsedJob:
    category: str
    title: str
    workers_needed: int | None = None
    pay_amount: float | None = None
    pay_unit: str | None = None
    pay_timing: str | None = None
    date: dt.date | None = None
    start_time: dt.time | None = None
    duration_hours: float | None = None
    metro: list[str] = field(default_factory=list)
    address: str | None = None
    phone: str | None = None
    description: str = ""


@dataclass
class ParseResult:
    kind: str
    scam_flags: list[str]
    jobs: list[ParsedJob]


def _date(value) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _time(value) -> time | None:
    try:
        return time.fromisoformat(value) if value else None
    except ValueError:
        return None


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def from_json(data: dict) -> ParseResult:
    """Приводит ответ модели к ParseResult, отбрасывая то, что не прошло проверку."""
    kind = data.get("kind") if data.get("kind") in ("job", "not_job", "spam") else "not_job"
    flags = [f for f in data.get("scam_flags") or [] if f in SCAM_FLAGS]
    jobs = []
    for j in data.get("jobs") or [] if kind == "job" else []:
        if not isinstance(j, dict) or not j.get("title"):
            continue
        workers = j.get("workers_needed")
        jobs.append(ParsedJob(
            category=j.get("category") if j.get("category") in CATEGORIES else "other",
            title=str(j["title"])[:120],
            workers_needed=workers if isinstance(workers, int) and 0 < workers < 1000 else None,
            pay_amount=_num(j.get("pay_amount")),
            pay_unit=j.get("pay_unit") if j.get("pay_unit") in PAY_UNITS else None,
            pay_timing=j.get("pay_timing") or None,
            date=_date(j.get("date")),
            start_time=_time(j.get("start_time")),
            duration_hours=_num(j.get("duration_hours")),
            metro=[m for m in j.get("metro") or [] if isinstance(m, str) and m.strip()],
            address=j.get("address") or None,
            phone=j.get("phone") or None,
            description=str(j.get("description") or "")[:500],
        ))
    if kind == "job" and not jobs:
        kind = "not_job"
    return ParseResult(kind, flags, jobs)


def user_prompt(text: str, sent_at: datetime) -> str:
    return f"Дата публикации: {sent_at:%Y-%m-%d %H:%M} (Москва), {_WEEKDAYS[sent_at.weekday()]}.\n\nСообщение:\n{text}"


_WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


class ParseError(Exception):
    pass


class ClaudeParser:
    def __init__(self, api_key: str | None, model: str):
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()
        self.model = model

    async def parse(self, text: str, sent_at: datetime) -> ParseResult:
        import anthropic

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_prompt(text, sent_at)}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            )
        except anthropic.RateLimitError as e:
            raise ParseError("rate limit") from e
        except anthropic.APIStatusError as e:
            raise ParseError(f"API {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ParseError("нет связи с API") from e
        if response.stop_reason == "refusal":
            return ParseResult("spam", [], [])
        if response.stop_reason == "max_tokens":
            raise ParseError("ответ модели обрезан")
        body = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return from_json(json.loads(body))
        except json.JSONDecodeError as e:
            raise ParseError("модель вернула не JSON") from e


class YandexParser:
    URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def __init__(self, api_key: str, folder_id: str, model: str):
        self.http = httpx.AsyncClient(timeout=60, headers={"Authorization": f"Api-Key {api_key}", "x-folder-id": folder_id})
        self.model_uri = f"gpt://{folder_id}/{model}"

    async def parse(self, text: str, sent_at: datetime) -> ParseResult:
        body = {
            "modelUri": self.model_uri,
            "completionOptions": {"stream": False, "temperature": 0.1, "maxTokens": "3000"},
            "messages": [
                {"role": "system", "text": SYSTEM_PROMPT + "\n\nОтветь только JSON по схеме:\n" + json.dumps(SCHEMA, ensure_ascii=False)},
                {"role": "user", "text": user_prompt(text, sent_at)},
            ],
            "jsonObject": True,
        }
        try:
            resp = await self.http.post(self.URL, json=body)
        except httpx.HTTPError as e:
            raise ParseError(f"нет связи с YandexGPT: {e}") from e
        if resp.status_code != 200:
            raise ParseError(f"YandexGPT {resp.status_code}: {resp.text[:200]}")
        try:
            answer = resp.json()["result"]["alternatives"][0]["message"]["text"]
            answer = answer.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            return from_json(json.loads(answer))
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise ParseError("YandexGPT вернул не JSON") from e


def make_parser(settings):
    if settings.llm_provider == "yandex":
        if not settings.yandex_api_key or not settings.yandex_folder_id:
            raise SystemExit("Для YandexGPT задайте YANDEX_GPT_API_KEY и YANDEX_FOLDER_ID в .env")
        return YandexParser(settings.yandex_api_key, settings.yandex_folder_id, settings.yandex_gpt_model)
    return ClaudeParser(settings.anthropic_api_key, settings.claude_model)
