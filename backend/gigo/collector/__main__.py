"""Сборщик: аккаунт Telegram читает чаты-источники и складывает сообщения в базу.

Аккаунт только читает: никаких сообщений, реакций и отметок о прочтении.

    python -m gigo.collector login     # один раз: вход в аккаунт-сборщик (код из Telegram)
    python -m gigo.collector join      # вступить в следующие чаты из sources.txt (по JOIN_BATCH за запуск)
    python -m gigo.collector backfill  # подтянуть историю за BACKFILL_DAYS дней
    python -m gigo.collector run       # история + чтение новых сообщений в реальном времени
    python -m gigo.collector stats     # сколько собрано по каждому чату
    python -m gigo.collector export    # выборка сообщений в data/sample.jsonl для проверки парсера
"""

import argparse
import asyncio
import json
import logging
import random
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, errors, events, utils
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import ChatInviteAlready, User

from gigo import config, db
from gigo.collector.convert import to_raw
from gigo.collector.sources import SourceLink, from_canonical, read_sources

log = logging.getLogger("gigo.collector")

REFRESH_SOURCES_EVERY = 600  # секунд: подхватить чаты, в которые вступили через join


def make_client(settings: config.Settings) -> TelegramClient:
    settings.require_telegram()
    return TelegramClient(
        str(settings.session_path),
        settings.tg_api_id,
        settings.tg_api_hash,
        flood_sleep_threshold=120,  # короткие FloodWait Telethon переждёт сам
        lang_code="ru",
        system_lang_code="ru-RU",
    )


async def connect(settings: config.Settings) -> TelegramClient:
    client = make_client(settings)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise SystemExit("Аккаунт не авторизован. Сначала выполните: python -m gigo.collector login")
    return client


# --- login ---------------------------------------------------------------

async def cmd_login(settings: config.Settings) -> None:
    client = make_client(settings)
    await client.start()  # спросит телефон, код и пароль 2FA
    me = await client.get_me()
    print(f"Вошли как {me.first_name} (id {me.id}). Сессия: {settings.session_path}.session")
    await client.disconnect()


# --- join ----------------------------------------------------------------

async def _join(client: TelegramClient, link: SourceLink):
    """Вступает в чат и возвращает его entity."""
    if link.kind == "invite":
        info = await client(CheckChatInviteRequest(link.value))
        if isinstance(info, ChatInviteAlready):
            return info.chat
        updates = await client(ImportChatInviteRequest(link.value))
        return updates.chats[0]
    entity = await client.get_entity(link.value)
    if isinstance(entity, User):
        raise ValueError("это пользователь или бот, а не чат")
    await client(JoinChannelRequest(entity))
    return entity


async def cmd_join(settings: config.Settings) -> None:
    links, bad = read_sources(settings.sources_file)
    for line in bad:
        print(f"Не понял строку в sources.txt, пропускаю: {line}")
    pool = await db.connect(settings.database_url)
    added = await db.upsert_source_links(pool, [link.canonical for link in links])
    if added:
        print(f"Новых чатов в sources.txt: {added}")

    pending = await db.pending_sources(pool, settings.join_batch)
    if not pending:
        print("Все чаты из sources.txt уже обработаны.")
        await pool.close()
        return

    client = await connect(settings)
    for i, source in enumerate(pending):
        if i:
            delay = random.randint(settings.join_delay_min, settings.join_delay_max)
            print(f"  пауза {delay} с перед следующим чатом…")
            await asyncio.sleep(delay)
        link = from_canonical(source["link"])
        try:
            entity = await _join(client, link)
        except errors.FloodWaitError as e:
            print(f"Telegram просит подождать {e.seconds} с. Останавливаюсь, повторите join позже.")
            break
        except errors.InviteRequestSentError:
            await db.mark_error(pool, source["id"], "отправлена заявка, ждём одобрения админа")
            print(f"{source['link']}: отправлена заявка на вступление")
            continue
        except (errors.InviteHashExpiredError, errors.InviteHashInvalidError,
                errors.UsernameNotOccupiedError, errors.UsernameInvalidError,
                errors.ChannelPrivateError, ValueError) as e:
            await db.mark_error(pool, source["id"], f"{type(e).__name__}: {e}", disable=True)
            print(f"{source['link']}: не получилось ({e}), источник выключен")
            continue
        except errors.ChannelsTooMuchError:
            print("Аккаунт состоит в максимуме чатов, вступать больше некуда.")
            break
        chat_id = utils.get_peer_id(entity)
        await db.mark_joined(pool, source["id"], chat_id, getattr(entity, "username", None), entity.title)
        print(f"{source['link']}: вступили в «{entity.title}»")

    left = len(await db.pending_sources(pool, 10_000))
    if left:
        print(f"Осталось вступить: {left}. Запустите join ещё раз позже (лучше не чаще раза в час).")
    await client.disconnect()
    await pool.close()


# --- backfill / run -----------------------------------------------------

async def backfill_chat(client: TelegramClient, pool, source, since: datetime) -> int:
    chat_id = source["chat_id"]
    last = await db.last_message_id(pool, chat_id)
    batch, total = [], 0
    async for msg in client.iter_messages(chat_id, min_id=last or 0):
        if msg.date < since:
            break
        if raw := to_raw(msg, chat_id, source["username"]):
            batch.append(raw)
        if len(batch) >= 200:
            await db.save_messages(pool, batch)
            total += len(batch)
            batch = []
    await db.save_messages(pool, batch)
    return total + len(batch)


async def backfill_all(client: TelegramClient, pool, settings: config.Settings) -> None:
    since = datetime.now(timezone.utc) - timedelta(days=settings.backfill_days)
    for source in await db.joined_sources(pool):
        try:
            n = await backfill_chat(client, pool, source, since)
            log.info("история «%s»: +%d сообщений", source["title"], n)
        except (errors.ChannelPrivateError, ValueError) as e:
            await db.mark_error(pool, source["id"], f"{type(e).__name__}: {e}")
            log.warning("история «%s»: %s", source["title"], e)


async def cmd_backfill(settings: config.Settings) -> None:
    pool = await db.connect(settings.database_url)
    client = await connect(settings)
    await client.get_dialogs()  # прогреть кэш чатов, чтобы находить их по id
    await backfill_all(client, pool, settings)
    await client.disconnect()
    await pool.close()


async def cmd_run(settings: config.Settings) -> None:
    pool = await db.connect(settings.database_url)
    client = await connect(settings)
    await client.get_dialogs()

    usernames: dict[int, str | None] = {}

    async def refresh_sources() -> None:
        rows = await db.joined_sources(pool)
        usernames.clear()
        usernames.update({r["chat_id"]: r["username"] for r in rows})

    await refresh_sources()
    if not usernames:
        log.warning("Нет ни одного чата-источника. Добавьте ссылки в sources.txt и выполните join.")

    async def on_message(event) -> None:
        if event.chat_id not in usernames:
            return
        if raw := to_raw(event.message, event.chat_id, usernames[event.chat_id]):
            await db.save_messages(pool, [raw])
            log.debug("сообщение %s/%s", event.chat_id, event.message.id)

    client.add_event_handler(on_message, events.NewMessage(incoming=True))
    client.add_event_handler(on_message, events.MessageEdited(incoming=True))

    log.info("Подтягиваю историю по %d чатам…", len(usernames))
    await backfill_all(client, pool, settings)
    log.info("Слушаю новые сообщения.")

    async def refresher() -> None:
        while True:
            await asyncio.sleep(REFRESH_SOURCES_EVERY)
            before = set(usernames)
            await refresh_sources()
            if set(usernames) - before:
                await client.get_dialogs()
                await backfill_all(client, pool, settings)

    task = asyncio.create_task(refresher())
    try:
        await client.run_until_disconnected()
    finally:
        task.cancel()
        await pool.close()


# --- stats / export -----------------------------------------------------

async def cmd_stats(settings: config.Settings) -> None:
    pool = await db.connect(settings.database_url)
    rows = await pool.fetch("""
        SELECT s.link, s.title, s.enabled, s.chat_id IS NOT NULL AS joined, s.last_error,
               count(m.id) AS total,
               count(m.id) FILTER (WHERE m.sent_at > now() - interval '24 hours') AS day
        FROM sources s LEFT JOIN raw_messages m ON m.chat_id = s.chat_id
        GROUP BY s.id ORDER BY total DESC, s.id
    """)
    if not rows:
        print("Источников пока нет. Добавьте ссылки в sources.txt и выполните join.")
    for r in rows:
        state = "ок" if r["joined"] else ("выключен" if not r["enabled"] else "не вступили")
        note = f"  ({r['last_error']})" if r["last_error"] else ""
        print(f"{r['total']:>7} всего {r['day']:>6} за сутки  [{state}] {r['title'] or r['link']}{note}")
    total = await pool.fetchval("SELECT count(*) FROM raw_messages")
    print(f"\nВсего сообщений: {total}")
    await pool.close()


async def cmd_export(settings: config.Settings, limit: int) -> None:
    pool = await db.connect(settings.database_url)
    rows = await pool.fetch(
        "SELECT id, chat_id, message_id, sent_at, text, link FROM raw_messages ORDER BY random() LIMIT $1", limit
    )
    path = settings.data_dir / "sample.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            item = dict(r)
            item["sent_at"] = item["sent_at"].isoformat()
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Записал {len(rows)} сообщений в {path}")
    await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m gigo.collector", description="Сборщик сообщений из чатов")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("login", "join", "backfill", "run", "stats"):
        sub.add_parser(name)
    export = sub.add_parser("export")
    export.add_argument("--limit", type=int, default=200)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)

    settings = config.load()
    commands = {
        "login": lambda: cmd_login(settings),
        "join": lambda: cmd_join(settings),
        "backfill": lambda: cmd_backfill(settings),
        "run": lambda: cmd_run(settings),
        "stats": lambda: cmd_stats(settings),
        "export": lambda: cmd_export(settings, args.limit),
    }
    asyncio.run(commands[args.cmd]())


if __name__ == "__main__":
    main()
