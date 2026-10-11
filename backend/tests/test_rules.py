from datetime import date, datetime, time, timezone

import pytest

from gigo.format import pay_line, when_line
from gigo import rules

TAGANKA_POST = "Нужны 2 грузчика м.Таганская сегодня к 14:00, переезд офиса ~4ч, 500р/час, оплата сразу"


@pytest.mark.parametrize("text, flag", [
    ("Работа курьером, высокий доход от 150 000 в неделю, пиши в лс", "drugs"),
    ("Нужны кладмены, оплата каждый день", "drugs"),
    ("Оформи карту Тинькофф и получи 3000р", "bank_card"),
    ("Ищем дропов, оплата сразу", "bank_card"),
    ("Удалённая работа с криптой, USDT", "crypto"),
    ("Для трудоустройства нужно оплатить обучение 2000р", "prepayment"),
])
def test_scam_flags(text, flag):
    assert flag in rules.scam_flags(text)


@pytest.mark.parametrize("text", [
    TAGANKA_POST,
    "Требуется кладовщик на склад, 3500 за смену",
    "Курьер пеший, 400р/час, выплаты раз в неделю",
    "Продавец-консультант, оплата на карту каждую неделю",
    "Нужны грузчики, оплата сразу, медкнижка не нужна",
    "Комплектовщик на склад Wildberries, 2500 смена",
])
def test_legit_jobs_not_flagged(text):
    assert rules.scam_flags(text) == []


def test_pay_per_hour():
    assert rules.pay_per_hour(500, "hour", 4) == (500, False)
    assert rules.pay_per_hour(3600, "shift", 12) == (300, False)
    assert rules.pay_per_hour(2400, "shift", None) == (300, True)
    assert rules.pay_per_hour(2000, "task", None) == (None, False)
    assert rules.pay_per_hour(None, "hour", 4) == (None, False)
    assert rules.pay_total(500, "hour", 4) == 2000
    assert rules.pay_total(3000, "shift", None) == 3000


def test_expires_at():
    created = datetime(2026, 10, 11, 10, 2, tzinfo=timezone.utc)
    start = rules.starts_at(date(2026, 10, 11), time(14, 0))
    assert rules.expires_at(created, date(2026, 10, 11), start) == datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    assert rules.expires_at(created, date(2026, 10, 12), None).isoformat() == "2026-10-13T00:00:00+03:00"
    assert (rules.expires_at(created, None, None) - created).days == 3


def test_format_lines():
    assert pay_line(500, False, 2000, 500, "hour", "сразу") == "500 ₽/ч · ≈2 000 ₽ · сразу"
    assert pay_line(300, True, 2400, 2400, "shift", None) == "≈300 ₽/ч · 2 400 ₽ за смену"
    assert pay_line(None, False, 5000, 5000, "task", None) == "5 000 ₽ за работу"
    assert pay_line(None, False, None, None, None, None) is None
    today = date(2026, 10, 11)
    start = rules.starts_at(today, time(14, 0))
    assert when_line(today, start, 4, today) == "сегодня 14:00 · ~4 ч"
    assert when_line(date(2026, 10, 12), None, None, today) == "завтра"
    assert when_line(None, None, None, today) is None
