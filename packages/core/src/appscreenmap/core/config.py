"""Crawl configuration: defaults, overridable from a TOML file and CLI flags."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

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
    blocked_text: list[str] = field(default_factory=lambda: list(DEFAULT_BLOCKED_TEXT))
    inputs: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_INPUTS))
    default_input: str = "test"
    # Fraction of the screen height masked at the top/bottom during visual diffs (status / nav bars).
    diff_mask_top: float = 0.045
    diff_mask_bottom: float = 0.0

    def __post_init__(self) -> None:
        self._blocked = [re.compile(p, re.IGNORECASE) for p in self.blocked_text]
        self._inputs = [(re.compile(k, re.IGNORECASE), v) for k, v in self.inputs.items()]

    def is_blocked(self, label: str) -> bool:
        return bool(label) and any(p.search(label) for p in self._blocked)

    def input_for(self, *hints: str) -> str:
        haystack = " ".join(h for h in hints if h)
        for pattern, value in self._inputs:
            if pattern.search(haystack):
                return value
        return self.default_input

    def missing_secrets(self, env=os.environ) -> list[str]:
        """Environment variables named by input placeholders that aren't set."""
        names = {n for v in [*self.inputs.values(), self.default_input] for n in placeholders(v)}
        return sorted(n for n in names if n not in env)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides) -> CrawlConfig:
        data: dict = {}
        if path:
            raw = tomllib.loads(Path(path).read_text())
            data.update(raw.get("crawl", {}))
            if "safety" in raw and "blocked_text" in raw["safety"]:
                blocked = list(raw["safety"]["blocked_text"])
                if raw["safety"].get("extend_defaults", True):
                    blocked = DEFAULT_BLOCKED_TEXT + blocked
                data["blocked_text"] = blocked
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
