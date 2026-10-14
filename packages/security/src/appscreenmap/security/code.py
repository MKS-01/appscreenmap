"""Static code checks over the dex files of an APK: API and class names the app references, no decompiling.

A dex file keeps every string once, as a length byte, the text and a NUL, so a method or class name the app uses
can be found with an exact byte match. A hit means the code references that API, not that the call is unsafe:
every finding is a candidate to read in the source, and SDKs bundled in the app are included.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

_MAX_ENTRY = 40 * 1024 * 1024
_DEX = re.compile(r"^classes\d*\.dex$")


def _lit(text: str) -> re.Pattern[bytes]:
    """A whole dex string: its length byte, the text, then NUL."""
    raw = text.encode()
    return re.compile(re.escape(bytes([len(raw)]) + raw + b"\0"))


def _any(text: str) -> re.Pattern[bytes]:
    return re.compile(re.escape(text.encode()))


# (rule, key, subject, severity or None for the rule's own, what the code does, pattern)
CODE_CHECKS: list[tuple[str, str, str, str | None, str, re.Pattern[bytes]]] = [
    (
        "webview-js-interface",
        "addjavascriptinterface",
        "addJavascriptInterface",
        None,
        "The code calls WebView.addJavascriptInterface; check which pages the WebView can load.",
        _lit("addJavascriptInterface"),
    ),
    (
        "insecure-trust-manager",
        "allow-all-hostname-verifier",
        "accept-all hostname verifier",
        None,
        "The code references the accept-all hostname verifier (ALLOW_ALL_HOSTNAME_VERIFIER), which skips hostname checks.",
        _lit("ALLOW_ALL_HOSTNAME_VERIFIER"),
    ),
    (
        "insecure-trust-manager",
        "allow-all-hostname-verifier",
        "accept-all hostname verifier",
        None,
        "The code references the accept-all hostname verifier (AllowAllHostnameVerifier), which skips hostname checks.",
        _any("org/apache/http/conn/ssl/AllowAllHostnameVerifier"),
    ),
    (
        "weak-crypto",
        "des",
        "DES",
        "warning",
        'The code names the DES cipher (a "DES" or "DES/…" Cipher.getInstance string).',
        re.compile(rb"(?:\x03DES|[\x07-\x40]DES/[A-Za-z0-9]+/[A-Za-z0-9]+)\x00"),
    ),
    (
        "weak-crypto",
        "rc4",
        "RC4",
        "warning",
        "The code names the RC4 cipher.",
        re.compile(rb"(?:\x03RC4|\x07ARCFOUR)\x00"),
    ),
    (
        "weak-crypto",
        "md5",
        "MD5",
        "info",
        'The code names the MD5 hash (a "MD5" MessageDigest string); fine for a checksum, not for security.',
        _lit("MD5"),
    ),
    (
        "weak-crypto",
        "sha-1",
        "SHA-1",
        "info",
        'The code names the SHA-1 hash (a "SHA-1" MessageDigest string); fine for a checksum, not for security.',
        re.compile(rb"(?:\x05SHA-1|\x04SHA1)\x00"),
    ),
    (
        "sticky-broadcast",
        "sendstickybroadcast",
        "sendStickyBroadcast",
        None,
        "The code calls sendStickyBroadcast.",
        _lit("sendStickyBroadcast"),
    ),
    (
        "sticky-broadcast",
        "sendstickyorderedbroadcast",
        "sendStickyOrderedBroadcast",
        None,
        "The code calls sendStickyOrderedBroadcast.",
        _lit("sendStickyOrderedBroadcast"),
    ),
    (
        "webview-file-access",
        "setallowuniversalaccessfromfileurls",
        "setAllowUniversalAccessFromFileURLs",
        None,
        "The code calls WebSettings.setAllowUniversalAccessFromFileURLs; check it passes false.",
        _lit("setAllowUniversalAccessFromFileURLs"),
    ),
    (
        "webview-file-access",
        "setallowfileaccessfromfileurls",
        "setAllowFileAccessFromFileURLs",
        None,
        "The code calls WebSettings.setAllowFileAccessFromFileURLs; check it passes false.",
        _lit("setAllowFileAccessFromFileURLs"),
    ),
    (
        "webview-file-access",
        "setallowfileaccess",
        "setAllowFileAccess",
        "info",
        "The code calls WebSettings.setAllowFileAccess; check it passes false unless file:// pages are needed.",
        _lit("setAllowFileAccess"),
    ),
    (
        "dynamic-code-loading",
        "dexclassloader",
        "DexClassLoader",
        None,
        "The code references DexClassLoader, which loads code from a file at runtime.",
        _any("Ldalvik/system/DexClassLoader;"),
    ),
    (
        "dynamic-code-loading",
        "inmemorydexclassloader",
        "InMemoryDexClassLoader",
        None,
        "The code references InMemoryDexClassLoader, which loads code from memory at runtime.",
        _any("Ldalvik/system/InMemoryDexClassLoader;"),
    ),
]


def scan_dex_bytes(data: bytes, where: str) -> list[dict]:
    out = []
    for rule, key, subject, severity, detail, pat in CODE_CHECKS:
        if pat.search(data):
            f = {"rule": rule, "key": key, "subject": subject, "detail": f"{detail} Found in {where}."}
            if severity:
                f["severity"] = severity
            out.append(f)
    return out


def scan_code(apk: str | Path) -> list[dict]:
    """Findings from every classes*.dex of the APK; a check that hits in several files is reported once."""
    seen: set[str] = set()
    out: list[dict] = []
    with zipfile.ZipFile(apk) as z:
        for info in sorted(z.infolist(), key=lambda i: i.filename):
            if _DEX.match(info.filename) and 0 < info.file_size <= _MAX_ENTRY:
                for f in scan_dex_bytes(z.read(info), info.filename):
                    if f["key"] not in seen:
                        seen.add(f["key"])
                        out.append(f)
    return out
