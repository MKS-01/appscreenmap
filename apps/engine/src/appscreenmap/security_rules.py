"""The security audit's rule catalogue (security_rules.json): loaded and validated here, read by the viewer too.

A rule says what is checked, why it matters, how to fix it and which official page backs it. Whether a rule is
`planned` or `ready` decides how the viewer shows it. Documented in .claude/skills/security-rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from urllib.parse import urlparse

PATH = Path(__file__).with_name("security_rules.json")
SEVERITIES = ("error", "warning", "info")
PLATFORMS = ("android", "ios", "both")
STATUSES = ("planned", "ready")
# Only first-party documentation backs a rule (same policy as web/src/insights/sources.ts).
OFFICIAL_HOSTS = (
    "developer.android.com",
    "developer.apple.com",
    "support.google.com",
    "source.android.com",
    "www.w3.org",
)


@dataclass(frozen=True)
class Ref:
    title: str
    url: str
    publisher: str


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    platform: str
    category: str
    severity: str
    needs: tuple[str, ...]
    status: str
    why: str
    fix: str
    refs: tuple[Ref, ...] = field(default_factory=tuple)


class RuleError(ValueError):
    pass


def _rule(raw: dict, categories: dict) -> Rule:
    missing = [
        k
        for k in ("id", "title", "platform", "category", "severity", "needs", "status", "why", "fix", "refs")
        if k not in raw
    ]
    if missing:
        raise RuleError(f"rule {raw.get('id', '?')}: missing {', '.join(missing)}")
    rid = raw["id"]
    if raw["severity"] not in SEVERITIES:
        raise RuleError(f"{rid}: severity must be one of {SEVERITIES}")
    if raw["platform"] not in PLATFORMS:
        raise RuleError(f"{rid}: platform must be one of {PLATFORMS}")
    if raw["status"] not in STATUSES:
        raise RuleError(f"{rid}: status must be one of {STATUSES}")
    if raw["category"] not in categories:
        raise RuleError(f"{rid}: unknown category {raw['category']!r}")
    if not raw["refs"]:
        raise RuleError(f"{rid}: a rule needs at least one official reference")
    refs = []
    for r in raw["refs"]:
        url = urlparse(r["url"])
        if url.scheme != "https" or url.hostname not in OFFICIAL_HOSTS:
            raise RuleError(
                f"{rid}: {r['url']} is not an official https source ({', '.join(OFFICIAL_HOSTS)})"
            )
        refs.append(Ref(r["title"], r["url"], r["publisher"]))
    return Rule(
        rid,
        raw["title"],
        raw["platform"],
        raw["category"],
        raw["severity"],
        tuple(raw["needs"]),
        raw["status"],
        raw["why"],
        raw["fix"],
        tuple(refs),
    )


@cache
def load_rules(path: str | Path = PATH) -> tuple[Rule, ...]:
    data = json.loads(Path(path).read_text())
    if data.get("schema") != 1:
        raise RuleError(f"unsupported security_rules schema {data.get('schema')!r}")
    rules = tuple(_rule(r, data["categories"]) for r in data["rules"])
    ids = [r.id for r in rules]
    if len(set(ids)) != len(ids):
        raise RuleError("duplicate rule ids: " + ", ".join(sorted({i for i in ids if ids.count(i) > 1})))
    return rules


def rules_for(platform: str) -> list[Rule]:
    """Rules that apply to a platform ('android' or 'ios'), including the cross-platform ones."""
    return [r for r in load_rules() if r.platform in (platform, "both")]
