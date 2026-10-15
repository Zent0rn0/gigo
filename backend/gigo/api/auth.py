"""Проверка initData из Telegram Mini App.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from gigo.i18n import N_

MAX_AGE = 24 * 3600


@dataclass(frozen=True)
class TgUser:
    id: int
    username: str | None = None
    first_name: str | None = None
    language_code: str | None = None


class InitDataError(ValueError):
    pass


def validate_init_data(init_data: str, bot_token: str, now: float | None = None) -> TgUser:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received = pairs.pop("hash", None)
    if not received:
        raise InitDataError(N_("нет подписи"))
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InitDataError(N_("подпись не сходится"))
    try:
        auth_date = int(pairs.get("auth_date", "0") or 0)
    except ValueError as e:
        raise InitDataError(N_("неверная дата входа")) from e
    if (now or time.time()) - auth_date > MAX_AGE:
        raise InitDataError(N_("данные устарели"))
    try:
        user = json.loads(pairs["user"])
        uid = int(user["id"])
        username, first_name = user.get("username"), user.get("first_name")
        language_code = user.get("language_code")
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        raise InitDataError(N_("нет пользователя")) from e
    if not 0 < uid < 2**63:
        raise InitDataError(N_("нет пользователя"))
    return TgUser(uid, username if isinstance(username, str) else None,
                  first_name if isinstance(first_name, str) else None,
                  language_code if isinstance(language_code, str) else None)
