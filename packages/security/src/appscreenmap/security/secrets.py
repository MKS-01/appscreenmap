"""Hard-coded secrets: high-confidence patterns over the raw bytes of dex files, resources and assets.

A finding keeps where the secret is, its length and a sha256 fingerprint, never the value.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

# High-confidence formats only. Words like "password" or "api_key" alone are not matched: they appear in
# every SDK and would bury the real findings.
SECRET_PATTERNS: list[tuple[str, re.Pattern[bytes], str]] = [
    ("AWS access key id", re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}"), "error"),
    ("Private key", re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"), "error"),
    ("Stripe live secret key", re.compile(rb"sk_live_[0-9a-zA-Z]{24,}"), "error"),
    ("Slack token", re.compile(rb"xox[baprs]-[0-9A-Za-z-]{10,}"), "error"),
    ("GitHub token", re.compile(rb"gh[pousr]_[0-9A-Za-z]{36,}"), "error"),
    (
        "Database URL with credentials",
        re.compile(
            rb"(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|amqps?)://[^\s:/@'\"]+:[^\s@/'\"]+@[^\s'\"]+"
        ),
        "error",
    ),
    ("Google API key", re.compile(rb"AIza[0-9A-Za-z_\-]{35}"), "info"),
]
_KIND_NOTE = {
    "Google API key": " Client API keys are meant to ship in apps; make sure this one is restricted to your package name and signing certificate.",
}
_SCANNED = re.compile(r"^(classes\d*\.dex|resources\.arsc|assets/.+|res/raw/.+)$")
_MAX_ENTRY = 24 * 1024 * 1024


def scan_bytes(data: bytes, where: str) -> list[dict]:
    """Secret findings in one blob. The value is never kept: only its length and a short sha256 fingerprint."""
    hits: dict[tuple[str, str], dict] = {}
    for kind, pat, severity in SECRET_PATTERNS:
        for m in pat.finditer(data):
            raw = m.group(0)
            if b"EXAMPLE" in raw.upper():
                continue
            fp = hashlib.sha256(raw).hexdigest()[:8]
            hits.setdefault(
                (kind, fp),
                {
                    "rule": "hardcoded-secret",
                    "key": f"{kind.lower().replace(' ', '-')}:{fp}",
                    "subject": kind,
                    "severity": severity,
                    "detail": f"{kind} ({len(raw)} characters, sha256 {fp}…) in {where}.{_KIND_NOTE.get(kind, '')}",
                },
            )
    return list(hits.values())


def scan_secrets(apk: str | Path) -> list[dict]:
    out: list[dict] = []
    with zipfile.ZipFile(apk) as z:
        for info in z.infolist():
            if _SCANNED.match(info.filename) and 0 < info.file_size <= _MAX_ENTRY:
                out.extend(scan_bytes(z.read(info), info.filename))
    seen, unique = set(), []
    for f in out:  # the same secret in two files is one finding, reported in the first
        if f["key"] not in seen:
            seen.add(f["key"])
            unique.append(f)
    return unique
