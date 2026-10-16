"""Crawl configuration: defaults, overridable from a TOML file and CLI flags."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import accounts, locales

# Steps a playbook may use (each a table in [[playbook.before]] / [[playbook.after]]). Exactly one action per step.
PLAYBOOK_ACTIONS = ("tap", "tap_at", "type", "wait", "scroll", "back", "restart", "pause", "account", "entry")
PLAYBOOK_PHASES = ("before", "after")


def validate_playbook(playbook: dict) -> None:
    for phase, steps in playbook.items():
        if phase not in PLAYBOOK_PHASES:
            raise ValueError(f"playbook phase must be one of {', '.join(PLAYBOOK_PHASES)}, got {phase!r}")
        for i, step in enumerate(steps, 1):
            acts = [a for a in PLAYBOOK_ACTIONS if a in step]
            if len(acts) != 1:
                raise ValueError(
                    f"playbook.{phase} step {i}: use exactly one of {', '.join(PLAYBOOK_ACTIONS)}"
                )
            if acts[0] == "type" and "value" not in step:
                raise ValueError(f"playbook.{phase} step {i}: `type` needs a `value`")
            if acts[0] == "scroll" and step["scroll"] not in ("end", "down", "up", "top"):
                raise ValueError(f"playbook.{phase} step {i}: scroll is end, down, up or top")
            if acts[0] == "tap_at" and not (
                isinstance(step["tap_at"], list)
                and len(step["tap_at"]) == 2
                and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in step["tap_at"])
            ):
                raise ValueError(f"playbook.{phase} step {i}: tap_at is [x, y] as fractions of the screen")
            if acts[0] == "entry" and step["entry"] is not True:
                raise ValueError(f"playbook.{phase} step {i}: entry can only be true")
            if acts[0] == "account" and step["account"] != "created":
                raise ValueError(f'playbook.{phase} step {i}: account can only be "created"')


# What a form field of each kind gets, for the words in any language (locales.json). Same values as DEFAULT_INPUTS.
LOCALE_INPUT_VALUES = {
    "password": "Passw0rd!",
    "email": "qa.tester@example.com",
    "phone": "5551234567",
    "postal": "94105",
    "otp": "123456",
    "last_name": "Tester",
    "first_name": "Qa",
    "search": "test",
}

DEFAULT_BLOCKED_TEXT = [
    r"\blog ?out\b",
    r"\bsign ?out\b",
    r"\bdelete\b",
    r"\bremove account\b",
    r"\bdeactivate\b",
    r"\buninstall\b",
    r"\bfactory reset\b",
    r"\berase\b",
    r"\bwipe\b",
    r"\breset (all|app|everything|data|device)\b",
    r"\bclear (all )?(app )?data\b",
    r"\bpay\b",
    r"\bpay now\b",
    r"\bpurchase\b",
    r"\bbuy\b",
    r"\bsubscribe\b",
    r"\bplace order\b",
    r"\bcall\b",
    r"\bdial\b",
    r"\breport\b",
]

# Resource ids are mostly English even in an app shown in another language (`btn_logout`, `deleteAccount`), so they
# are a language-free second check. A short list: ids like `call_to_action` or `report_list` must not be blocked.
DEFAULT_BLOCKED_IDS = [
    r"\blog ?out\b",
    r"\bsign ?out\b",
    r"\bdelete\b",
    r"\bremove account\b",
    r"\bdeactivate\b",
    r"\buninstall\b",
    r"\bfactory reset\b",
    r"\bpurchase\b",
    r"\bbuy\b",
    r"\bsubscribe\b",
    r"\bplace order\b",
    r"\bpay now\b",
]
_ID_SPLIT_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|[_\-.:/]+")

# Matched in order against "resource-id hint text content-desc" of an input (case-insensitive).
DEFAULT_INPUTS: dict[str, str] = {
    r"pass(word|code)?|\bpin\b": "Passw0rd!",
    r"e-?mail|username|user_?name|login": "qa.tester@example.com",
    r"phone|mobile|\btel\b": "5551234567",
    r"zip|postal|pin.?code": "94105",
    r"otp|code|verification": "123456",
    r"first.?name": "Qa",
    r"last.?name|surname": "Tester",
    r"name": "QA Tester",
    r"search|query|find": "test",
    r"url|website|link": "https://example.com",
    r"city": "San Francisco",
    r"address|street": "1 Market St",
    r"age|amount|qty|quantity|number|count": "1",
    r"date": "2026-01-15",
}


# `${NAME}` in an input value is read from the environment when it is typed. The placeholder, never the
# value, is what ends up in map.json, the Maestro flows and the trace (Maestro reads `${NAME}` too).
PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class MissingSecret(KeyError):
    """An input placeholder names an environment variable that isn't set."""

    def __str__(self) -> str:
        return f"environment variable {self.args[0]} is not set (used as ${{{self.args[0]}}} in [inputs])"


def placeholders(value: str) -> list[str]:
    return PLACEHOLDER_RE.findall(value or "")


def resolve(value: str, env=os.environ) -> str:
    """Fill `${NAME}` placeholders from the environment. Raises MissingSecret for unset names."""

    def sub(m: re.Match) -> str:
        if m.group(1) not in env:
            raise MissingSecret(m.group(1))
        return env[m.group(1)]

    return PLACEHOLDER_RE.sub(sub, value)


@dataclass
class CrawlConfig:
    max_steps: int = 300
    max_minutes: float = 30.0
    max_depth: int = 15
    # Stop once this many steps in a row found no new screen: the map has saturated. 0 disables.
    stop_after_no_new: int = 30
    settle_seconds: float = 0.8
    launch_wait_seconds: float = 2.5
    similarity: float = 0.80
    max_list_items: int = 2
    # Tab tour: visit every bottom-nav / tab destination once, and on each take at most `tour_taps` other action
    # (one layer deeper), instead of exploring everything. Combine with max_depth = 2.
    tab_tour: bool = False
    tour_taps: int = 1
    max_scrolls: int = 3
    explore_toggles: bool = True
    long_click: bool = False
    fill_forms: bool = True
    # Pin the app (lock task mode) so nothing can take it out of the foreground: BACK at the root
    # screen and links that open other apps are blocked. Anything that still leaves is never repeated.
    stay_in_app: bool = True
    clear_data: bool = False
    grant_permissions: bool = True
    disable_animations: bool = True
    # Navigation performance: wait for the app to stop drawing instead of a fixed sleep, and record
    # how long each screen took to load (see perf.py). Off = fixed settle_seconds sleeps, no timings.
    measure_load: bool = True
    load_quiet_ms: int = 400  # no new frames for this long = screen settled
    load_timeout_s: float = 10.0  # give up waiting (continuous animation, polling UI)
    perf_budget_ms: int = 1000  # median load above this is "needs work", above 2.5× is "slow"
    # Crawl at a system font scale (e.g. 2.0 for WCAG 1.4.4 Resize Text); 0 keeps the device setting.
    font_scale: float = 0.0
    allow_permission_dialogs: bool = True
    # The language the app is crawled in (a tag like "fr-FR", "ja", "ar"). "" keeps the device or app setting.
    # Android sets the app's own language (Android 13+); iOS relaunches the app with that language.
    locale: str = ""
    # Languages whose destructive-button and form-field words are used besides English: ["all"] or codes like ["es", "ja"].
    languages: list[str] = field(default_factory=lambda: ["all"])
    # The email template of the saved test account ({rand} = random hex), and scripted steps run before the
    # exploration and after it (sign up, then later tap through profile and settings and log out).
    account_email: str = accounts.DEFAULT_EMAIL
    playbook: dict = field(default_factory=dict)
    blocked_text: list[str] = field(default_factory=lambda: list(DEFAULT_BLOCKED_TEXT))
    inputs: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_INPUTS))
    default_input: str = "test"
    # Fraction of the screen height masked at the top/bottom during visual diffs (status / nav bars).
    diff_mask_top: float = 0.045
    diff_mask_bottom: float = 0.0

    def __post_init__(self) -> None:
        # Your own rules and English first; the other languages' words are added behind them.
        self._blocked = [
            re.compile(p, re.IGNORECASE)
            for p in [*self.blocked_text, *locales.blocked_patterns(self.languages)]
        ]
        self._blocked_ids = [re.compile(p) for p in DEFAULT_BLOCKED_IDS]
        rules = [(re.compile(k, re.IGNORECASE), v) for k, v in self.inputs.items()]
        extra = [
            (re.compile(pat, re.IGNORECASE), LOCALE_INPUT_VALUES[kind])
            for kind, pat in locales.input_patterns(self.languages).items()
        ]
        # The other languages' field words go in front of the catch-all `name` rule, so "Nachname" is a last name.
        at = next((i for i, (p, _) in enumerate(rules) if p.pattern == "name"), len(rules))
        self._inputs = rules[:at] + extra + rules[at:]

    def is_blocked(self, label: str) -> bool:
        return bool(label) and any(p.search(label) for p in self._blocked)

    def is_blocked_id(self, rid: str) -> bool:
        """A resource id like `btn_logout` or `deleteAccount`, whatever language the screen is in."""
        words = _ID_SPLIT_RE.sub(" ", rid or "").lower()
        return bool(words.strip()) and any(p.search(words) for p in self._blocked_ids)

    def input_for(self, *hints: str) -> str:
        haystack = " ".join(h for h in hints if h)
        for pattern, value in self._inputs:
            if pattern.search(haystack):
                return value
        return self.default_input

    def missing_secrets(self, env=os.environ) -> list[str]:
        """Environment variables named by input placeholders that aren't set."""
        values = [*self.inputs.values(), self.default_input]
        values += [str(s.get("value", "")) for steps in self.playbook.values() for s in steps]
        names = {n for v in values for n in placeholders(v)} - set(
            accounts.ACCOUNT_VARS
        )  # the saved account supplies these
        return sorted(n for n in names if n not in env)

    def uses_account(self) -> bool:
        """Does anything refer to ${ACCOUNT_EMAIL} / ${ACCOUNT_PASSWORD}, or mark the account as created?"""
        values = [*self.inputs.values(), self.default_input]
        steps = [s for st in self.playbook.values() for s in st]
        values += [str(s.get("value", "")) for s in steps]
        return any(set(placeholders(v)) & set(accounts.ACCOUNT_VARS) for v in values) or any(
            "account" in s for s in steps
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides) -> CrawlConfig:
        data: dict = {}
        if path:
            raw = tomllib.loads(Path(path).read_text())
            data.update(raw.get("crawl", {}))
            if "languages" in raw.get("safety", {}):
                data["languages"] = list(raw["safety"]["languages"])
            if "safety" in raw and "blocked_text" in raw["safety"]:
                blocked = list(raw["safety"]["blocked_text"])
                if raw["safety"].get("extend_defaults", True):
                    blocked = DEFAULT_BLOCKED_TEXT + blocked
                data["blocked_text"] = blocked
            if "account" in raw:
                if unknown := set(raw["account"]) - {"email"}:
                    raise ValueError(f"Unknown [account] keys: {', '.join(sorted(unknown))}")
                if "email" in raw["account"]:
                    data["account_email"] = raw["account"]["email"]
            if "playbook" in raw:
                validate_playbook(raw["playbook"])
                data["playbook"] = {k: list(v) for k, v in raw["playbook"].items()}
            if "inputs" in raw:
                inputs = dict(raw["inputs"])
                data["default_input"] = inputs.pop("default", cls.default_input)
                # User rules take precedence over the built-in ones.
                data["inputs"] = {**inputs, **{k: v for k, v in DEFAULT_INPUTS.items() if k not in inputs}}
        data.update({k: v for k, v in overrides.items() if v is not None})
        known = set(cls.__dataclass_fields__)
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown config keys: {', '.join(sorted(unknown))}")
        return cls(**data)
