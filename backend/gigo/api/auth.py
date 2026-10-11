"""Проверка initData из Telegram Mini App.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

MAX_AGE = 24 * 3600


@dataclass(frozen=True)
class TgUser:
    id: int
    username: str | None = None
    first_name: str | None = None


class InitDataError(ValueError):
    pass


def validate_init_data(init_data: str, bot_token: str, now: float | None = None) -> TgUser:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received = pairs.pop("hash", None)
    if not received:
        raise InitDataError("нет подписи")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InitDataError("подпись не сходится")
    auth_date = int(pairs.get("auth_date", "0") or 0)
    if (now or time.time()) - auth_date > MAX_AGE:
        raise InitDataError("данные устарели")
    try:
        user = json.loads(pairs["user"])
        return TgUser(int(user["id"]), user.get("username"), user.get("first_name"))
    except (KeyError, ValueError, TypeError) as e:
        raise InitDataError("нет пользователя") from e
