"""Перевод сообщения Telethon в строку таблицы raw_messages."""

from telethon import utils
from telethon.tl.types import PeerChannel

from gigo.db import RawMessage

# Короче этого объявление о работе не бывает: «+», «спасибо», стикеры подписями.
MIN_TEXT_LEN = 15


def message_link(chat_id: int, message_id: int, username: str | None) -> str | None:
    if username:
        return f"https://t.me/{username}/{message_id}"
    real_id, peer_type = utils.resolve_id(chat_id)
    if peer_type is PeerChannel:
        # Ссылка на приватный канал или супергруппу открывается у участников.
        return f"https://t.me/c/{real_id}/{message_id}"
    return None  # у обычных групп ссылок на сообщения нет


def to_raw(message, chat_id: int, username: str | None) -> RawMessage | None:
    """None, если сообщение не стоит сохранять (сервисное, пустое, слишком короткое)."""
    text = (getattr(message, "message", None) or "").strip()
    if len(text) < MIN_TEXT_LEN or getattr(message, "action", None) is not None:
        return None
    return RawMessage(
        chat_id=chat_id,
        message_id=message.id,
        sender_id=getattr(message, "sender_id", None),
        sent_at=message.date,
        edited_at=getattr(message, "edit_date", None),
        text=text,
        link=message_link(chat_id, message.id, username),
    )
