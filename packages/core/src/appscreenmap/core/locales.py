"""Crawl safety and form-fill words in many languages (locales.json), as regexes the crawl config can add.

English stays in config.py. Every language here is a word list, not a regex: contributors add words, this module
turns them into patterns (whole words for Latin and Cyrillic, plain substrings for scripts without spaces).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

PATH = Path(__file__).with_name("locales.json")
INPUT_KINDS = ("password", "email", "phone", "postal", "otp", "last_name", "first_name", "search")


class LocaleError(ValueError):
    pass


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    boundary: bool
    blocked: tuple[str, ...]
    inputs: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def base(self) -> str:
        return self.code.split("-")[0]


def _word(term: str, boundary: bool) -> str:
    """One term as a regex: spaces match any run of spaces, an apostrophe matches both kinds."""
    pat = r"\s+".join(re.escape(part).replace("'", "['’]") for part in term.split())
    return rf"(?<!\w)(?:{pat})(?!\w)" if boundary else pat


@cache
def load_languages(path: Path = PATH) -> tuple[Language, ...]:
    data = json.loads(path.read_text())
    out, seen = [], set()
    for raw in data["languages"]:
        code = raw.get("code", "")
        if not code or code in seen:
            raise LocaleError(f"missing or duplicate language code: {code!r}")
        seen.add(code)
        blocked = tuple(raw.get("blocked", ()))
        if not blocked:
            raise LocaleError(f"{code}: no blocked words")
        inputs = {k: tuple(v) for k, v in raw.get("inputs", {}).items()}
        for k in inputs:
            if k not in INPUT_KINDS:
                raise LocaleError(f"{code}: unknown input kind {k!r}")
        for term in (*blocked, *(t for v in inputs.values() for t in v)):
            if not isinstance(term, str) or len(term.strip()) < 2:
                raise LocaleError(f"{code}: every word needs at least two characters, got {term!r}")
        out.append(Language(code, raw["name"], bool(raw["boundary"]), blocked, inputs))
    return tuple(out)


def select(languages: list[str] | None = None) -> list[Language]:
    """The languages named by `languages` (codes like `fr` or `zh-Hans`; `all` or None = every one)."""
    every = load_languages()
    if not languages or "all" in languages:
        return list(every)
    wanted = {c.lower() for c in languages}
    return [lang for lang in every if lang.code.lower() in wanted or lang.base.lower() in wanted]


def blocked_patterns(languages: list[str] | None = None) -> list[str]:
    """One regex per language matching its destructive or costly button words."""
    return ["|".join(_word(t, lang.boundary) for t in lang.blocked) for lang in select(languages)]


def input_patterns(languages: list[str] | None = None) -> dict[str, list[str]]:
    """Per input kind (email, phone, …): one regex over every selected language's field-label words."""
    words: dict[str, list[str]] = {k: [] for k in INPUT_KINDS}
    for lang in select(languages):
        for kind, terms in lang.inputs.items():
            words[kind].extend(re.escape(t) for t in terms)
    return {k: "|".join(v) for k, v in words.items() if v}


def covers(locale: str) -> bool:
    """Do we have words for this language tag (`fr-CA`, `ja`, `zh-Hant-TW`)? English counts."""
    tag = locale.replace("_", "-").strip()
    if not tag:
        return True
    primary = tag.split("-")[0].lower()
    if primary == "en":
        return True
    for lang in load_languages():
        if lang.code.lower() == tag.lower() or lang.code.lower().startswith(tag.lower() + "-"):
            return True
        if lang.base.lower() == primary and "-" not in lang.code:
            return True
        if primary == "zh" and lang.base == "zh":
            script = {"hant": "zh-Hant", "tw": "zh-Hant", "hk": "zh-Hant", "mo": "zh-Hant"}
            parts = [p.lower() for p in tag.split("-")[1:]]
            want = next((script[p] for p in parts if p in script), "zh-Hans")
            if lang.code == want:
                return True
    return False
