"""Ключи переводов бота и API: русские тексты из tr("…"), N_("…") и plural(n, "…|…|…").

python -m gigo.i18n_keys check          — в каждом gigo/locales/<язык>.json есть все ключи и совпадают подстановки
python -m gigo.i18n_keys missing <язык> — JSON с непереведёнными ключами (для переводчика)
"""

import ast
import json
import re
import sys
from pathlib import Path

from gigo.i18n import DEFAULT, LANGUAGES

PKG = Path(__file__).parent
LOCALES = PKG / "locales"
SKIP = {"i18n.py", "i18n_keys.py", "demo.py"}


def _literal(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def collect() -> tuple[list[str], list[str]]:
    keys: set[str] = set()
    problems: list[str] = []
    for path in sorted(PKG.rglob("*.py")):
        if path.name in SKIP:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            where = f"{path.relative_to(PKG.parent)}:{node.lineno}"
            if name in ("tr", "N_") and node.args:
                s = _literal(node.args[0])
                if s is not None:
                    keys.add(s)
                elif isinstance(node.args[0], ast.JoinedStr) or name == "N_":
                    problems.append(f"{where}: {name}() с f-строкой или не строкой")
            elif name == "plural" and len(node.args) >= 2:
                s = _literal(node.args[1])
                if s is not None and s.count("|") == 2:
                    keys.add(s)
                else:
                    problems.append(f"{where}: plural() без строки «a|b|c»")
    return sorted(keys), problems


def _ph(s: str) -> list[str]:
    return sorted(re.findall(r"\{(\w*)\}", s))


def check() -> tuple[list[str], list[str]]:
    keys, errors = collect()
    for lang in LANGUAGES:
        if lang == DEFAULT:
            continue
        path = LOCALES / f"{lang}.json"
        if not path.exists():
            errors.append(f"{lang}: нет файла")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        missing = [k for k in keys if not d.get(k)]
        if missing:
            errors.append(f"{lang}: нет перевода для {len(missing)}: {missing[:5]}")
        for k in keys:
            v = d.get(k)
            if v and _ph(k) != _ph(v):
                errors.append(f"{lang}: подстановки не совпадают: {k!r} → {v!r}")
            if v and v.count("<") != k.count("<"):
                errors.append(f"{lang}: HTML-теги не совпадают: {k!r} → {v!r}")
        extra = [k for k in d if k not in keys]
        if extra:
            errors.append(f"{lang}: лишние ключи ({len(extra)}): {extra[:5]}")
    return keys, errors


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "keys":
        ks, ps = collect()
        print("\n".join(ps), file=sys.stderr)
        print(json.dumps(ks, ensure_ascii=False, indent=2))
    elif cmd == "missing":
        lang = sys.argv[2]
        p = LOCALES / f"{lang}.json"
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        print(json.dumps({k: "" for k in collect()[0] if not d.get(k)}, ensure_ascii=False, indent=2))
    else:
        ks, errs = check()
        print("\n".join(errs), file=sys.stderr)
        print(f"ключей: {len(ks)}, ошибок: {len(errs)}")
        sys.exit(1 if errs else 0)
