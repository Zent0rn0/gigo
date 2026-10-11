"""Разбор файла sources.txt со ссылками на чаты-источники."""

import re
from dataclasses import dataclass
from pathlib import Path

_INVITE = re.compile(r"^(?:https?://)?(?:t|telegram)\.me/(?:\+|joinchat/)([\w-]+)/?$", re.I)
_PUBLIC = re.compile(r"^(?:https?://)?(?:t|telegram)\.me/(?:s/)?([a-z][\w]{3,})(?:/\d+)?/?(?:\?.*)?$", re.I)
_AT = re.compile(r"^@([a-z][\w]{3,})$", re.I)


@dataclass(frozen=True)
class SourceLink:
    kind: str  # "username" | "invite"
    value: str

    @property
    def canonical(self) -> str:
        return f"@{self.value}" if self.kind == "username" else f"+{self.value}"


def parse_link(raw: str) -> SourceLink | None:
    text = raw.strip()
    if m := _INVITE.match(text):
        return SourceLink("invite", m.group(1))
    if m := (_PUBLIC.match(text) or _AT.match(text)):
        return SourceLink("username", m.group(1).lower())
    return None


def from_canonical(link: str) -> SourceLink:
    if link.startswith("+"):
        return SourceLink("invite", link[1:])
    return SourceLink("username", link.lstrip("@"))


def read_sources(path: Path) -> tuple[list[SourceLink], list[str]]:
    """Возвращает (ссылки без повторов, строки, которые не удалось разобрать)."""
    links: dict[str, SourceLink] = {}
    bad: list[str] = []
    if not path.exists():
        return [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        link = parse_link(line)
        if link is None:
            bad.append(line)
        else:
            links.setdefault(link.canonical, link)
    return list(links.values()), bad
