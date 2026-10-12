"""Внешний вид бота: баннеры над сообщениями и премиум-эмодзи вместо обычных.

Баннеры: картинки в gigo/bot/banners/<имя>.png|jpg. Нет файла — сообщение уходит текстом.

Премиум-эмодзи (Bot API 9.4+): бот может вставлять custom emoji в свои сообщения и на кнопки, если у владельца
бота есть Telegram Premium. В .env: CUSTOM_EMOJI_SETS=имя_набора[,ещё] (из ссылки t.me/addemoji/<имя>).
При старте бот берёт из наборов, какой премиум-эмодзи соответствует какому обычному, и подменяет их на лету
во всех исходящих сообщениях и кнопках. Если Telegram откажет (нет Premium), бот один раз переотправит
сообщение с обычными эмодзи и больше подмену не делает.
"""

import logging
import os
import re
from pathlib import Path

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageCaption, EditMessageReplyMarkup, EditMessageText, SendMessage, SendPhoto
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message

log = logging.getLogger("gigo.bot")

BANNERS_DIR = Path(os.getenv("BANNERS_DIR", Path(__file__).parent / "banners"))
CAPTION_LIMIT = 1024
_VS = "️"


# --- баннеры ------------------------------------------------------------------

class Banners:
    """Картинки над сообщениями. После первой отправки Telegram отдаёт file_id, дальше шлём его."""

    def __init__(self, directory: Path = BANNERS_DIR):
        self.dir = directory
        self.file_ids: dict[str, str] = {}

    def path(self, name: str) -> Path | None:
        for ext in ("png", "jpg", "jpeg", "webp"):
            p = self.dir / f"{name}.{ext}"
            if p.is_file():
                return p
        return None

    def available(self, name: str | None, text: str) -> bool:
        return bool(name) and len(_plain(text)) <= CAPTION_LIMIT and (name in self.file_ids or self.path(name))

    def photo(self, name: str):
        if name in self.file_ids:
            return self.file_ids[name]
        p = self.path(name)
        return BufferedInputFile(p.read_bytes(), filename=p.name)

    def remember(self, name: str, sent: Message) -> None:
        if sent and getattr(sent, "photo", None):
            self.file_ids[name] = sent.photo[-1].file_id


BANNERS = Banners()


def _plain(html: str) -> str:
    """Длина подписи считается без HTML-тегов."""
    return re.sub(r"<[^>]+>", "", html).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


async def show(message: Message, text: str, markup=None, banner: str | None = None) -> Message:
    """Ответ в чат: с баннером, если картинка есть и текст влезает в подпись, иначе обычным сообщением."""
    if BANNERS.available(banner, text):
        try:
            sent = await message.answer_photo(BANNERS.photo(banner), caption=text, reply_markup=markup)
            BANNERS.remember(banner, sent)
            return sent
        except TelegramBadRequest as e:
            log.warning("баннер %s не отправился: %s", banner, e)
    return await message.answer(text, reply_markup=markup)


async def send(bot, chat_id: int, text: str, markup=None, banner: str | None = None, **kw):
    """То же для рассылок из фоновых задач."""
    if BANNERS.available(banner, text):
        try:
            sent = await bot.send_photo(chat_id, BANNERS.photo(banner), caption=text, reply_markup=markup)
            BANNERS.remember(banner, sent)
            return sent
        except TelegramBadRequest as e:
            if "chat not found" in str(e).lower() or "blocked" in str(e).lower():
                raise
            log.warning("баннер %s не отправился: %s", banner, e)
    return await bot.send_message(chat_id, text, reply_markup=markup, **kw)


async def edit(message: Message, text: str, markup=None) -> None:
    """Меняет текст сообщения; у сообщения с баннером меняется подпись."""
    if message.photo:
        if len(_plain(text)) > CAPTION_LIMIT:
            raise TelegramBadRequest(method=None, message="caption is too long")
        await message.edit_caption(caption=text, reply_markup=markup)
    else:
        await message.edit_text(text, reply_markup=markup)


# --- премиум-эмодзи -------------------------------------------------------------

class CustomEmoji:
    """Обычный эмодзи → id премиум-эмодзи."""

    def __init__(self):
        self.ids: dict[str, str] = {}
        self.enabled = False
        self._re: re.Pattern | None = None

    def set(self, mapping: dict[str, str]) -> None:
        self.ids = {k.replace(_VS, ""): v for k, v in mapping.items() if k}
        self.enabled = bool(self.ids)
        keys = sorted(self.ids, key=len, reverse=True)
        self._re = re.compile("|".join(re.escape(k) + _VS + "?" for k in keys)) if keys else None

    def _id(self, emoji: str) -> str | None:
        return self.ids.get(emoji.replace(_VS, ""))

    def html(self, text: str | None) -> str | None:
        """Подменяет эмодзи в HTML-тексте на <tg-emoji>. Внутри уже вставленных и внутри тегов не трогает."""
        if not text or not self.enabled or not self._re:
            return text
        out, pos = [], 0
        for m in re.finditer(r"<tg-emoji[^>]*>.*?</tg-emoji>|<[^>]+>", text, re.S):
            out.append(self._sub(text[pos:m.start()]))
            out.append(m.group(0))
            pos = m.end()
        out.append(self._sub(text[pos:]))
        return "".join(out)

    def _sub(self, chunk: str) -> str:
        return self._re.sub(lambda m: f'<tg-emoji emoji-id="{self._id(m.group(0))}">{m.group(0)}</tg-emoji>', chunk)

    def markup(self, markup):
        """Эмодзи в начале подписи кнопки уходит в icon_custom_emoji_id."""
        if not self.enabled or not isinstance(markup, InlineKeyboardMarkup):
            return markup
        rows = []
        for row in markup.inline_keyboard:
            new_row = []
            for b in row:
                m = self._re.match(b.text) if self._re else None
                if m and not b.icon_custom_emoji_id and b.text[m.end():].strip():
                    b = b.model_copy(update={"icon_custom_emoji_id": self._id(m.group(0)),
                                             "text": b.text[m.end():].strip()})
                new_row.append(b)
            rows.append(new_row)
        return InlineKeyboardMarkup(inline_keyboard=rows)


EMOJI = CustomEmoji()


async def load_custom_emoji(bot, sets: list[str]) -> int:
    """Читает наборы премиум-эмодзи. Возвращает, сколько обычных эмодзи получили замену."""
    mapping: dict[str, str] = {}
    for name in sets:
        try:
            st = await bot.get_sticker_set(name)
        except Exception as e:
            log.warning("набор эмодзи %s не загрузился: %s", name, e)
            continue
        for s in st.stickers:
            if s.emoji and s.custom_emoji_id:
                mapping.setdefault(s.emoji, s.custom_emoji_id)
    EMOJI.set(mapping)
    return len(EMOJI.ids)


class PrettyMiddleware(BaseRequestMiddleware):
    """Подставляет премиум-эмодзи в исходящие сообщения; при отказе Telegram откатывается на обычные."""

    async def __call__(self, make_request, bot, method):
        if not EMOJI.enabled:
            return await make_request(bot, method)
        update = {}
        if isinstance(method, (SendMessage, EditMessageText)):
            update["text"] = EMOJI.html(method.text)
        elif isinstance(method, (SendPhoto, EditMessageCaption)):
            update["caption"] = EMOJI.html(method.caption)
        if isinstance(method, (SendMessage, EditMessageText, SendPhoto, EditMessageCaption, EditMessageReplyMarkup)):
            update["reply_markup"] = EMOJI.markup(method.reply_markup)
        if not update:
            return await make_request(bot, method)
        try:
            return await make_request(bot, method.model_copy(update=update))
        except TelegramBadRequest as e:
            text = str(e).lower()
            if "emoji" not in text and "entit" not in text and "icon" not in text:
                raise
            log.warning("премиум-эмодзи недоступны (нужен Telegram Premium у владельца бота): %s", e)
            EMOJI.enabled = False
            return await make_request(bot, method)
