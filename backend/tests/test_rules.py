from datetime import date, datetime, time, timezone

import pytest

from gigo.format import pay_line, when_line
from gigo.parser import rules
from gigo.parser.geo import MetroIndex, Station
from gigo.parser.llm import SCHEMA, from_json

TAGANKA_POST = ("СРОЧНО!!! нужны 2 грузчика м.Таганская сегодня к 14:00, переезд офиса ~4ч, 500р/час, "
                "оплата сразу. звонить 8 900 123-45-67")


def test_looks_like_job():
    assert rules.looks_like_job(TAGANKA_POST)
    assert rules.looks_like_job("Требуются упаковщики на склад, смена 12 часов")
    assert not rules.looks_like_job("Всем привет! Как дела?")
    assert not rules.looks_like_job("спасибо, договорились")


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


def test_phone():
    assert rules.extract_phone(TAGANKA_POST) == "79001234567"
    assert rules.extract_phone("+7 (915) 000-11-22 Иван") == "79150001122"
    assert rules.extract_phone("оплата 500 руб") is None
    assert rules.normalize_phone("8-900-123-45-67") == "79001234567"


def test_text_hash_ignores_decoration():
    assert rules.text_hash("Нужны 2 грузчика! 🔥🔥") == rules.text_hash("нужны 2 ГРУЗЧИКА")
    assert rules.text_hash("Нужны 2 грузчика") != rules.text_hash("Нужны 3 грузчика")


def test_pay_per_hour():
    assert rules.pay_per_hour(500, "hour", 4) == (500, False)
    assert rules.pay_per_hour(3600, "shift", 12) == (300, False)
    assert rules.pay_per_hour(2400, "shift", None) == (300, True)
    assert rules.pay_per_hour(2000, "task", None) == (None, False)
    assert rules.pay_per_hour(70400, "month", None) == (400, True)
    assert rules.pay_per_hour(None, "hour", 4) == (None, False)
    assert rules.pay_total(500, "hour", 4) == 2000
    assert rules.pay_total(3000, "shift", None) == 3000


def test_expires_at():
    sent = datetime(2026, 10, 11, 10, 2, tzinfo=timezone.utc)
    start = rules.starts_at(date(2026, 10, 11), time(14, 0))
    assert rules.expires_at(sent, date(2026, 10, 11), start, 4, "hour") == datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    assert rules.expires_at(sent, date(2026, 10, 12), None, None, None).isoformat() == "2026-10-13T00:00:00+03:00"
    assert (rules.expires_at(sent, None, None, None, "month") - sent).days == 3
    assert (rules.expires_at(sent, None, None, None, "hour") - sent).total_seconds() == 24 * 3600


def test_metro_index():
    idx = MetroIndex([Station("7.1", "Таганская", 55.74, 37.65), Station("5.1", "Таганская", 55.74, 37.65),
                      Station("3.1", "Курская", 55.75, 37.66), Station("1.1", "Охотный Ряд", 55.75, 37.61),
                      Station("10.1", "Марьина Роща", 55.79, 37.61)])
    assert idx.find("м.Таганская").id == "7.1"
    assert idx.find("Таганской").id == "7.1"
    assert idx.find("Курской").id == "3.1"
    assert idx.find("охотный ряд").id == "1.1"
    assert idx.find("Марьиной Рощи").id == "10.1"
    assert idx.find("Выхино") is None
    assert idx.find("") is None


def test_from_json_validates():
    res = from_json({"kind": "job", "scam_flags": ["drugs", "made_up"], "jobs": [{
        "category": "loader", "title": "Грузчики ×2", "workers_needed": 2, "pay_amount": 500, "pay_unit": "hour",
        "pay_timing": "сразу", "date": "2026-10-11", "start_time": "14:00", "duration_hours": 4,
        "metro": ["Таганская"], "address": None, "phone": "8 900 123-45-67", "description": "Переезд офиса",
    }, {"category": "space", "title": "Что-то", "pay_unit": "year", "date": "завтра", "workers_needed": -1}]})
    assert res.kind == "job" and res.scam_flags == ["drugs"]
    a, b = res.jobs
    assert a.date == date(2026, 10, 11) and a.start_time == time(14, 0) and a.pay_amount == 500
    assert b.category == "other" and b.pay_unit is None and b.date is None and b.workers_needed is None
    assert from_json({"kind": "job", "scam_flags": [], "jobs": []}).kind == "not_job"
    assert from_json({"kind": "spam", "scam_flags": [], "jobs": [{"title": "x"}]}).jobs == []


def test_schema_is_strict():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(SCHEMA)


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
