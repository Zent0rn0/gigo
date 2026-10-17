"""Единый вид ошибок API и защита от сбоев.

Любой ответ с ошибкой: {"detail": "текст для человека", "code": "короткий_код", "request_id": "..."}.
detail всегда строка (Mini App показывает её как есть), code не меняется от текста и годится для логики.
Неожиданный сбой не отдаёт наружу трассировку: только общий текст и request_id, по которому его найти в логе.
"""

import asyncio
import json
import logging
import re
import secrets
from http import HTTPStatus

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from gigo import actions, i18n
from gigo.i18n import N_, tr

log = logging.getLogger("gigo.api")

MAX_BODY = 64 * 1024        # байт в теле запроса: самые большие формы весят пару килобайт
REQUEST_TIMEOUT = 30        # секунд на ответ API, дальше отвечаем 503, а не держим соединение

CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
         409: "conflict", 413: "too_large", 422: "invalid", 429: "rate_limited", 500: "internal",
         503: "unavailable", 504: "timeout"}

# Стандартные английские тексты Starlette («Not Found») заменяем русскими.
DEFAULT_TEXTS = {400: N_("Неверный запрос"), 401: N_("Нужен вход через Telegram"), 403: N_("Нет доступа"),
                 404: N_("Не найдено"), 405: N_("Такой запрос не поддерживается"), 413: N_("Слишком большой запрос"),
                 429: N_("Слишком много запросов. Подождите минуту."),
                 500: N_("Что-то пошло не так. Попробуйте ещё раз чуть позже."),
                 503: N_("Сервер сейчас недоступен. Попробуйте ещё раз через минуту.")}

DB_UNAVAILABLE = N_("База данных сейчас недоступна. Попробуйте ещё раз через минуту.")
DB_BUSY = N_("Сервер сейчас перегружен. Попробуйте ещё раз.")

_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(request: Request | None, status: int, detail: str, code: str | None = None,
                   headers: dict | None = None, **extra) -> JSONResponse:
    rid = request_id(request) if request else None
    # тексты ошибок — русские ключи: переводим на язык из заголовка X-Lang (выставлен в GuardMiddleware)
    detail = i18n.translate(detail)
    body = {"detail": detail, "code": code or CODES.get(status, "error"), **extra}
    if rid:
        body["request_id"] = rid
    headers = {**(headers or {}), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if rid:
        headers["X-Request-ID"] = rid
    return JSONResponse(body, status_code=status, headers=headers)


# --- ошибки валидации -----------------------------------------------------------

FIELD_NAMES = {
    "category": N_("Категория"), "title": N_("Название"), "description": N_("Описание"), "workers_needed": N_("Сколько человек"),
    "pay_amount": N_("Оплата"), "pay_unit": N_("Единица оплаты"), "pay_timing": N_("Когда оплата"), "starts_on": N_("Дата"),
    "start_time": N_("Время начала"), "duration_hours": N_("Длительность"), "metro_id": N_("Метро"), "address": N_("Адрес"),
    "lat": N_("Точка на карте"), "lng": N_("Точка на карте"), "message": N_("Сообщение"), "status": N_("Статус"),
    "rating": N_("Оценка"), "text": N_("Текст"), "reason": N_("Причина"), "role": N_("Роль"), "about": N_("О себе"),
    "skills": N_("Навыки"), "name": N_("Название"), "categories": N_("Категории"), "metro_ids": N_("Станции метро"),
    "pay_min": N_("Оплата от"), "radius_km": N_("Радиус"), "worker_id": N_("Исполнитель"), "response_id": N_("Отклик"),
    "q": N_("Поиск"), "limit": N_("Размер страницы"), "offset": N_("Страница"), "lang": N_("Язык"),
}


def _reason(err: dict) -> str:
    t, ctx = err.get("type", ""), err.get("ctx") or {}
    if t == "missing":
        return tr("заполните это поле")
    if t == "string_too_long":
        return tr("не длиннее {n} знаков", n=ctx.get("max_length"))
    if t == "string_too_short":
        return tr("не короче {n} знаков", n=ctx.get("min_length"))
    if t == "too_long":
        return tr("не больше {n} значений", n=ctx.get("max_length"))
    if t in ("greater_than", "greater_than_equal", "less_than", "less_than_equal", "finite_number"):
        return tr("значение вне допустимых границ")
    if t in ("int_parsing", "int_type", "int_from_float", "float_parsing", "float_type"):
        return tr("нужно число")
    if t in ("literal_error", "enum"):
        return tr("недопустимое значение")
    if t.startswith("date") or t.startswith("time"):
        return tr("неверная дата или время")
    if t == "string_pattern_mismatch":
        return tr("неверный формат")
    return tr("неверное значение")


def validation_message(errors: list[dict]) -> str:
    if not errors:
        return N_("Проверьте введённые данные")
    err = errors[0]
    if err.get("type") in ("json_invalid", "model_attributes_type", "dict_type") or err.get("loc") == ("body",):
        return N_("Неверный формат запроса")
    names = [str(x) for x in err.get("loc", ()) if isinstance(x, str) and x not in ("body", "query", "path", "header")]
    field = names[-1] if names else ""
    label = FIELD_NAMES.get(field)
    if label:
        return tr("{field}: {reason}", field=tr(label), reason=_reason(err))
    return tr("Проверьте введённые данные: {reason}", reason=_reason(err))


def _safe_errors(errors) -> list[dict]:
    """Без input и ctx: в них может быть всё тело запроса или объекты, которые не превращаются в JSON."""
    return [{"loc": [x if isinstance(x, (str, int)) else str(x) for x in e.get("loc", ())],
             "type": e.get("type"), "msg": e.get("msg")} for e in errors][:10]


# --- ошибки базы --------------------------------------------------------------

_DB_DOWN = (asyncpg.CannotConnectNowError, asyncpg.TooManyConnectionsError, asyncpg.ConnectionDoesNotExistError,
            asyncpg.InterfaceError, asyncpg.PostgresConnectionError, asyncpg.AdminShutdownError,
            asyncpg.CrashShutdownError)
_DB_BUSY = (asyncpg.QueryCanceledError, asyncpg.SerializationError, asyncpg.DeadlockDetectedError,
            asyncpg.LockNotAvailableError)


def db_error(request: Request, e: Exception) -> JSONResponse:
    if isinstance(e, _DB_DOWN):
        log.error("база недоступна: %s %s [%s]", type(e).__name__, request.url.path, request_id(request))
        return error_response(request, 503, DB_UNAVAILABLE, "db_unavailable", {"Retry-After": "10"})
    if isinstance(e, _DB_BUSY):
        log.warning("база занята: %s %s [%s]", type(e).__name__, request.url.path, request_id(request))
        return error_response(request, 503, DB_BUSY, "db_busy", {"Retry-After": "2"})
    if isinstance(e, asyncpg.UniqueViolationError):
        return error_response(request, 409, N_("Такая запись уже есть"), "duplicate")
    if isinstance(e, asyncpg.ForeignKeyViolationError):
        return error_response(request, 409, N_("Связанная запись не найдена или уже удалена"), "conflict")
    if isinstance(e, (asyncpg.DataError, asyncpg.IntegrityConstraintViolationError)):
        # DataError: число вне диапазона bigint, неверный формат и т.п.; Check/NotNull: нарушено ограничение таблицы
        log.warning("данные отклонены базой: %s %s [%s]", type(e).__name__, request.url.path, request_id(request))
        return error_response(request, 422, N_("Неверные данные в запросе"), "invalid")
    log.error("ошибка базы %s на %s [%s]", type(e).__name__, request.url.path, request_id(request), exc_info=e)
    return error_response(request, 500, DEFAULT_TEXTS[500], "internal")


# --- ASGI-прослойки ---------------------------------------------------------------

class GuardMiddleware:
    """Внешний слой для /api: request_id, ограничение размера тела и времени ответа.

    Чистый ASGI, а не @app.middleware: так таймаут не ломает потоковую передачу и срабатывает
    даже когда приложение зависло на ожидании соединения с базой.
    """

    def __init__(self, app, max_body: int = MAX_BODY, timeout: float = REQUEST_TIMEOUT):
        self.app = app
        self.max_body = max_body
        self.timeout = timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        # язык ответа: Mini App присылает выбранный язык в X-Lang
        i18n.set_lang(headers.get("x-lang"))
        rid = headers.get("x-request-id", "")
        rid = rid if _REQUEST_ID.match(rid) else secrets.token_hex(6)
        scope.setdefault("state", {})["request_id"] = rid
        is_api = scope.get("path", "").startswith("/api/")
        started = False
        too_large = False

        async def send_with_id(message):
            nonlocal started
            if too_large:  # ответ приложения на обрезанное тело заменяем своим 413
                return
            if message["type"] == "http.response.start":
                started = True
                raw = list(message.get("headers", []))
                if not any(k.lower() == b"x-request-id" for k, _ in raw):
                    raw.append((b"x-request-id", rid.encode()))
                message = {**message, "headers": raw}
            await send(message)

        async def fail(status: int, detail: str, code: str) -> None:
            nonlocal too_large
            if started:
                return
            too_large = False
            body = json.dumps({"detail": i18n.translate(detail), "code": code, "request_id": rid}, ensure_ascii=False).encode()
            await send_with_id({"type": "http.response.start", "status": status, "headers": [
                (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": body})

        if not is_api:
            return await self.app(scope, receive, send_with_id)

        length = headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_body):
            return await fail(413, DEFAULT_TEXTS[413], "too_large")

        received = 0

        async def limited_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    # Как приложение обернёт это исключение, неважно: его ответ отбросим и ответим 413.
                    too_large = True
                    raise _BodyTooLarge
            return message

        try:
            async with asyncio.timeout(self.timeout):
                await self.app(scope, limited_receive, send_with_id)
        except TimeoutError:
            if too_large:
                return await fail(413, DEFAULT_TEXTS[413], "too_large")
            log.error("запрос дольше %s с: %s %s [%s]", self.timeout, scope.get("method"), scope.get("path"), rid)
            return await fail(503, DB_BUSY, "timeout")
        except Exception:
            if not too_large:
                raise
        if too_large:
            await fail(413, DEFAULT_TEXTS[413], "too_large")


class _BodyTooLarge(Exception):
    pass


# --- регистрация ---------------------------------------------------------------------

def install(app: FastAPI) -> None:
    @app.exception_handler(actions.ActionError)
    async def action_error(request: Request, e: actions.ActionError):
        return error_response(request, e.status, e.detail)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, e: StarletteHTTPException):
        detail = e.detail if isinstance(e.detail, str) else None
        if not detail or detail == HTTPStatus(e.status_code).phrase:
            detail = DEFAULT_TEXTS.get(e.status_code, detail or N_("Ошибка"))
        # блокировку Mini App узнаёт по коду: текст переводится на язык пользователя
        code = "banned" if e.status_code == 403 and "заблокирован" in detail else None
        return error_response(request, e.status_code, detail, code, headers=getattr(e, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, e: RequestValidationError):
        errors = e.errors()
        return error_response(request, 422, validation_message(errors), "invalid", errors=_safe_errors(errors))

    @app.exception_handler(asyncpg.PostgresError)
    async def postgres_error(request: Request, e: asyncpg.PostgresError):
        return db_error(request, e)

    @app.exception_handler(asyncpg.InterfaceError)
    async def interface_error(request: Request, e: asyncpg.InterfaceError):
        return db_error(request, e)

    @app.exception_handler(OSError)
    async def os_error(request: Request, e: OSError):
        # база перезапускается или сеть до неё оборвалась: ConnectionRefusedError и т.п.
        log.error("сеть/ОС: %s на %s [%s]", type(e).__name__, request.url.path, request_id(request))
        return error_response(request, 503, DEFAULT_TEXTS[503], "unavailable", {"Retry-After": "10"})

    @app.exception_handler(TimeoutError)
    async def timeout_error(request: Request, e: TimeoutError):
        # command_timeout пула или ожидание свободного соединения
        log.warning("таймаут базы на %s [%s]", request.url.path, request_id(request))
        return error_response(request, 503, DB_BUSY, "db_busy", {"Retry-After": "2"})

    @app.exception_handler(Exception)
    async def unexpected(request: Request, e: Exception):
        log.error("сбой на %s %s [%s]", request.method, request.url.path, request_id(request), exc_info=e)
        return error_response(request, 500, DEFAULT_TEXTS[500], "internal")
