"""Обработчик сообщений: разбор ИИ в заказы.

    python -m gigo.parser run                      # разбирать новые сообщения непрерывно
    python -m gigo.parser test data/sample.jsonl   # проверить разбор на выборке, отчёт в data/parse_report.md
    python -m gigo.parser reset                    # стереть заказы и разобрать всё заново (после правки промпта)
"""

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from gigo import config, db
from gigo.categories import CATEGORIES, SCAM_FLAGS
from gigo.parser import rules
from gigo.parser.geo import Geocoder, MetroIndex
from gigo.parser.llm import ParseError, make_parser
from gigo.parser.pipeline import Processor, build_job, pending

log = logging.getLogger("gigo.parser")

BATCH = 50
IDLE_SLEEP = 5
ERROR_SLEEP = 30
METRO_RELOAD = 3600


async def cmd_run(settings: config.Settings) -> None:
    pool = await db.connect(settings.database_url)
    llm = make_parser(settings)
    metro = await MetroIndex.load(pool, "moscow")
    if not metro.exact:
        log.warning("Справочник метро пуст: выполните python -m gigo.metro, иначе заказы не попадут на карту")
    processor = Processor(pool, llm, metro, Geocoder(settings.yandex_geocoder_key, pool))
    sem = asyncio.Semaphore(settings.parser_concurrency)
    loaded_at = time.monotonic()
    max_age = timedelta(days=settings.backfill_days)

    async def one(msg) -> str:
        async with sem:
            return await processor.process(msg)

    log.info("Обработчик запущен (%s).", settings.llm_provider)
    while True:
        if time.monotonic() - loaded_at > METRO_RELOAD:
            processor.metro = await MetroIndex.load(pool, "moscow")
            loaded_at = time.monotonic()
        batch = await pending(pool, BATCH, max_age)
        if not batch:
            await asyncio.sleep(IDLE_SLEEP)
            continue
        results = await asyncio.gather(*(one(m) for m in batch), return_exceptions=True)
        stats: dict[str, int] = {}
        errors = [r for r in results if isinstance(r, Exception)]
        for r in results:
            key = "error" if isinstance(r, Exception) else r
            stats[key] = stats.get(key, 0) + 1
        log.info("разобрано %d: %s", len(batch), ", ".join(f"{k} {v}" for k, v in sorted(stats.items())))
        unexpected = [e for e in errors if not isinstance(e, ParseError)]
        for e in unexpected:
            log.error("ошибка обработки", exc_info=e)
        if errors:
            log.warning("ошибки разбора (%s), пауза %d с", errors[0], ERROR_SLEEP)
            await asyncio.sleep(ERROR_SLEEP)


async def cmd_test(settings: config.Settings, path: Path, limit: int) -> None:
    """Разбор выборки без записи в базу: смотрим глазами, как ИИ понимает объявления."""
    llm = make_parser(settings)
    try:
        pool = await db.connect(settings.database_url)
        metro = await MetroIndex.load(pool, "moscow")
    except OSError:
        pool, metro = None, MetroIndex([])
    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()][:limit]
    sem = asyncio.Semaphore(settings.parser_concurrency)

    async def one(item):
        sent_at = datetime.fromisoformat(item["sent_at"])
        text = item["text"]
        if not rules.looks_like_job(text):
            return item, "not_job (правила)", []
        async with sem:
            try:
                res = await llm.parse(text, sent_at.astimezone(rules.MSK))
            except ParseError as e:
                return item, f"ошибка: {e}", []
        flags = sorted(set(rules.scam_flags(text)) | set(res.scam_flags))
        jobs = [build_job(j, text, sent_at, flags, metro, None, "") for j in res.jobs]
        return item, res.kind + (f" ⚠ {', '.join(flags)}" if flags else ""), jobs

    results = await asyncio.gather(*(one(i) for i in items))
    out = ["# Проверка разбора\n"]
    counts: dict[str, int] = {}
    for item, kind, jobs in results:
        key = kind.split(":")[0].split()[0]
        counts[key] = counts.get(key, 0) + 1
        out.append(f"## {item.get('link') or item.get('id')} · {kind}\n")
        out.append("```text\n" + item["text"].strip() + "\n```\n")
        for j in jobs:
            label, emoji = CATEGORIES[j.category]
            pay = f"{j.pay_per_hour:.0f} ₽/ч" + (" (оценка)" if j.pay_estimated else "") if j.pay_per_hour else "оплата не указана"
            out.append(f"- {emoji} **{j.title}** · {label} · {pay}"
                       + (f" · всего {j.pay_total:.0f} ₽" if j.pay_total else ""))
            out.append(f"  - когда: {j.starts_at or j.starts_on or '—'}, {j.duration_hours or '?'} ч; "
                       f"метро: {j.metro_id or '—'}; адрес: {j.address or '—'}; тел: {j.phone or '—'}")
            out.append(f"  - {j.description}")
            if j.scam_flags:
                out.append("  - скрыт: " + "; ".join(SCAM_FLAGS[f] for f in j.scam_flags))
        out.append("")
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    out.insert(1, f"Сообщений: {len(results)}. {summary}\n")
    report = settings.data_dir / "parse_report.md"
    report.write_text("\n".join(out), encoding="utf-8")
    print(f"{summary}\nОтчёт: {report}")
    if pool:
        await pool.close()


async def cmd_reset(settings: config.Settings) -> None:
    pool = await db.connect(settings.database_url)
    await pool.execute("TRUNCATE jobs RESTART IDENTITY CASCADE")
    n = await pool.fetchval(
        "WITH u AS (UPDATE raw_messages SET processed_at = NULL, parse_status = NULL, parse_attempts = 0 RETURNING 1) "
        "SELECT count(*) FROM u"
    )
    print(f"Заказы удалены, сообщений к повторному разбору: {n}")
    await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m gigo.parser")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("reset")
    test = sub.add_parser("test")
    test.add_argument("file", type=Path)
    test.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpx2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    settings = config.load()
    if args.cmd == "run":
        asyncio.run(cmd_run(settings))
    elif args.cmd == "reset":
        asyncio.run(cmd_reset(settings))
    else:
        asyncio.run(cmd_test(settings, args.file, args.limit))


if __name__ == "__main__":
    main()
