from datetime import datetime, timezone
from types import SimpleNamespace

from gigo.collector.convert import message_link, to_raw
from gigo.collector.sources import SourceLink, parse_link, read_sources
from gigo.metro import parse_metro


def test_parse_link_variants():
    assert parse_link("https://t.me/Gruzchiki_Moskva") == SourceLink("username", "gruzchiki_moskva")
    assert parse_link("t.me/podrabotka_msk/12345") == SourceLink("username", "podrabotka_msk")
    assert parse_link("@podrabotka_msk") == SourceLink("username", "podrabotka_msk")
    assert parse_link("https://t.me/s/podrabotka_msk") == SourceLink("username", "podrabotka_msk")
    assert parse_link("https://t.me/+AbCdEf123_-x") == SourceLink("invite", "AbCdEf123_-x")
    assert parse_link("https://t.me/joinchat/AbCdEf") == SourceLink("invite", "AbCdEf")
    assert parse_link("просто текст") is None


def test_read_sources_dedups_and_reports_bad(tmp_path):
    f = tmp_path / "sources.txt"
    f.write_text("# комментарий\n@podrabotka_msk\nt.me/Podrabotka_MSK\n\nчто-то не то\nt.me/+Hash1 # приватный\n")
    links, bad = read_sources(f)
    assert [l.canonical for l in links] == ["@podrabotka_msk", "+Hash1"]
    assert bad == ["что-то не то"]


def test_message_link():
    assert message_link(-1001234567890, 5, "gruz") == "https://t.me/gruz/5"
    assert message_link(-1001234567890, 5, None) == "https://t.me/c/1234567890/5"
    assert message_link(-12345, 5, None) is None


def _msg(text, **kw):
    return SimpleNamespace(id=7, message=text, sender_id=42, action=None,
                           date=datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc), edit_date=None, **kw)


def test_to_raw_keeps_job_post():
    raw = to_raw(_msg("  Нужны 2 грузчика м.Таганская, 500р/час  "), -1001, "gruz")
    assert raw.text == "Нужны 2 грузчика м.Таганская, 500р/час"
    assert raw.link == "https://t.me/gruz/7"


def test_to_raw_skips_short_and_service():
    assert to_raw(_msg("+"), -1001, None) is None
    assert to_raw(_msg(None), -1001, None) is None
    service = _msg("Пользователь вступил в группу")
    service.action = object()
    assert to_raw(service, -1001, None) is None


def test_parse_metro():
    data = {"lines": [{"name": "Таганско-Краснопресненская", "hex_color": "943E90", "stations": [
        {"id": "7.1", "name": "Таганская", "lat": 55.7393, "lng": 37.6533},
        {"id": "7.2", "name": "Без координат", "lat": None, "lng": None},
    ]}]}
    assert parse_metro(data, "moscow") == [
        ("7.1", "moscow", "Таганско-Краснопресненская", "943E90", "Таганская", 37.6533, 55.7393)
    ]
