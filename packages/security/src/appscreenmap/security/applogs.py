"""Masking for the app's own log lines before they are written: typed secrets and token-shaped values.

A masked token keeps its kind and a short sha256 fingerprint, so `sensitive-logging` can report it without the value.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable

from .secrets import SECRET_PATTERNS

MASK = "••••"  # same as appscreenmap.core.activity
MIN_SECRET = 4
# Formats that show up in logs more than in binaries: auth headers and JWTs.
LOG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("JWT", re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}")),
    ("Bearer token", re.compile(r"(?i)(?<=bearer )[\w\-.~+/]{16,}=*")),
    *((kind, re.compile(p.pattern.decode())) for kind, p, _ in SECRET_PATTERNS),
]


def _fingerprint(kind: str, m: re.Match) -> str:
    return f"[{kind} · sha {hashlib.sha256(m.group(0).encode()).hexdigest()[:8]}]"


def masker(secrets: Iterable[str | None] = ()) -> Callable[[str], str]:
    """A function that masks typed `secrets` and every token-shaped value in one log line."""
    known = sorted({s for s in secrets if s and len(s) >= MIN_SECRET}, key=len, reverse=True)

    def mask(text: str) -> str:
        for s in known:
            text = text.replace(s, MASK)
        for kind, pat in LOG_PATTERNS:
            text = pat.sub(lambda m, k=kind: _fingerprint(k, m), text)
        return text

    return mask
