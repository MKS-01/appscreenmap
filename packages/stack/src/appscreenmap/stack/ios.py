"""Static fingerprints of an installed iOS app: its `.app` folder as the simulator holds it (Info.plist, Frameworks/,
bundle paths, the Mach-O load commands and strings of its binaries). Nothing is decompiled.

A debug build keeps its code in `<App>.debug.dylib` beside a stub executable, so both are read. An App Store
binary is FairPlay-encrypted: its strings are noise, so no `symbol` rule is matched on it.
"""

from __future__ import annotations

import os
import plistlib
import re
from pathlib import Path

from appscreenmap.store.facts import parse_ios_plist

from . import macho
from .detect import IOS_RULES, RANK, summarize
from .storage import IOS_STORAGE

_MAX_BINARY = 512 * 1024 * 1024
_MAX_PATHS = 100_000
_HEADERS = 4 * 1024 * 1024
# Database file names the code opens by name: C strings (Swift, Objective-C) and UTF-16 (Kotlin/Native literals).
_NAME = rb"[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}\.(?:db|sqlite|sqlite3)"
_DB_UTF8 = re.compile(rb"\x00(" + _NAME + rb")\x00")
_DB_UTF16 = re.compile(rb"((?:[A-Za-z0-9_.-]\x00){1,63}\.\x00(?:d\x00b\x00|s\x00q\x00l\x00i\x00t\x00e\x00))")
# Kotlin package names end in .db too (com.example.db): a reverse-domain name is a package, not a file.
_PACKAGE = re.compile(r"(?:com|org|net|dev|io|app|co|me|androidx|kotlinx)\.[a-z0-9_]+(?:\.[a-z0-9_]+)+")


def _plist(path: Path) -> dict:
    try:
        return plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {}


def _read(path: Path, notes: list[str]) -> bytes | None:
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size <= _MAX_BINARY:
                return f.read()
            notes.append(f"{path.name} is over {_MAX_BINARY >> 20} MB: only its headers were read.")
            head = f.read(_HEADERS)
            if found := macho.fat_slice(head):  # a fat file: the headers to read are at the slice's offset
                f.seek(found[0])
                return f.read(_HEADERS)
            return head
    except OSError as e:
        notes.append(f"{path.name} could not be read: {e}.")
        return None


def _db_names(blobs: list[bytes]) -> list[str]:
    names = set()
    for b in blobs:
        names |= {m.group(1).decode() for m in _DB_UTF8.finditer(b)}
        names |= {m.group(1).decode("utf-16le") for m in _DB_UTF16.finditer(b)}
    return sorted(n for n in names if not _PACKAGE.fullmatch(n))[:20]


def _match(kind: str, pattern: str, ctx: dict) -> list[str]:
    if kind == "framework":
        return [f"Frameworks/{pattern}.framework"] if pattern in ctx["frameworks"] else []
    if kind == "bundle-path":
        return next(([p] for p in ctx["paths"] if p.startswith(pattern)), [])
    if kind == "bundle-file":
        return next(([p] for p in ctx["paths"] if p.rsplit("/", 1)[-1] == pattern), [])
    if kind == "dylib":
        return next(([d] for d in ctx["dylibs"] if pattern in d), [])
    return [f"{pattern} in {name}" for name, b in ctx["blobs"] if pattern.encode() in b][:1]


def _signals(rules, ctx: dict) -> list[tuple[tuple, list[tuple[str, str]]]]:
    out = []
    for rule in rules:
        hits = [(conf, ev) for kind, pat, conf in rule[-1] for ev in _match(kind, pat, ctx)]
        if hits:
            out.append((rule, hits))
    return out


def _best(hits: list[tuple[str, str]]) -> str:
    return max(hits, key=lambda h: RANK[h[0]])[0]


def fingerprint_app(app: Path) -> dict:
    """Everything an `.app` folder shows without running it, in the shape `fingerprint` gives for APKs."""
    app = Path(app)
    notes: list[str] = []
    info = _plist(app / "Info.plist")
    if not info:
        notes.append(f"{app.name} has no readable Info.plist.")
    bundle = info.get("CFBundleIdentifier") or ""
    paths: list[str] = []
    for root, dirs, files in os.walk(app):
        dirs.sort()
        rel = Path(root).relative_to(app)
        for name in [*(d + "/" for d in dirs), *sorted(files)]:
            paths.append((rel / name).as_posix() + ("/" if name.endswith("/") else ""))
        if len(paths) > _MAX_PATHS:
            notes.append(f"Over {_MAX_PATHS} files in the bundle: the rest were not listed.")
            break

    frameworks: dict[str, dict] = {}
    binaries: list[Path] = []
    exe = info.get("CFBundleExecutable")
    main = app / exe if exe else None
    if main and main.is_file():
        binaries.append(main)
    debug = app / f"{exe}.debug.dylib" if exe else None
    if debug and debug.is_file():
        binaries.append(debug)
    fw_dir = app / "Frameworks"
    if fw_dir.is_dir():
        for fw in sorted(fw_dir.iterdir()):
            if fw.suffix == ".framework" and fw.is_dir():
                fw_info = _plist(fw / "Info.plist")
                frameworks[fw.stem] = {
                    "name": fw.stem,
                    **({"version": v} if (v := fw_info.get("CFBundleShortVersionString")) else {}),
                }
                binary = fw / (fw_info.get("CFBundleExecutable") or fw.stem)
                if binary.is_file():
                    binaries.append(binary)
            elif fw.suffix == ".dylib" and fw.is_file():
                frameworks[fw.name] = {"name": fw.name}
                binaries.append(fw)

    headers: dict[str, dict] = {}
    blobs: list[tuple[str, bytes]] = []
    for path in binaries:
        data = _read(path, notes)
        if data is None:
            continue
        mo = macho.parse(data)
        if mo is None:
            continue
        headers[path.name] = mo
        if mo["encrypted"]:
            notes.append(f"{path.name} is encrypted (an App Store build): its code was not read for markers.")
            continue
        blobs.append((path.name, data))
    head = headers.get(main.name) if main else None
    if main and head is None:
        notes.append(f"The main executable {exe} is missing or not Mach-O.")
    dylibs = sorted({d for p in (main, debug) if p and p.name in headers for d in headers[p.name]["dylibs"]})
    ctx = {"frameworks": set(frameworks), "paths": paths, "dylibs": dylibs, "blobs": blobs}

    signals = [
        {
            "id": rule[0],
            "label": rule[1],
            "category": rule[2],
            "confidence": _best(hits),
            "evidence": [ev for _, ev in hits],
            "source": "device",
        }
        for rule, hits in _signals(IOS_RULES, ctx)
    ]
    db_names = _db_names([b for _, b in blobs])
    storage = []
    for (sid, label, encrypted, locations, _), hits in _signals(IOS_STORAGE, ctx):
        locations = [loc.replace("{bundle}", bundle or "<bundle-id>") for loc in locations]
        if sid == "sqlite" and db_names:
            # SQLDelight's native driver keeps databases in Application Support/databases/ (checked on a simulator);
            # otherwise the folder is up to the code, so the name is all we know.
            kmp = any(sig["id"] == "kotlin-native" for sig in signals)
            folder = "Library/Application Support/databases/" if kmp else "**/"
            locations = [folder + n for n in db_names]
        storage.append(
            {
                "id": sid,
                "label": label,
                "encrypted": encrypted,
                "locations": locations,
                "confidence": _best(hits),
                "evidence": [ev for _, ev in hits],
                "source": "device",
            }
        )

    plist = parse_ios_plist(info) if info else {}
    encrypted = head["encrypted"] if head else None
    return {
        "app": app.name,
        "executable": exe,
        "debug_build": bool(debug and debug.is_file()),
        "bundle_id": bundle or None,
        "version": info.get("CFBundleShortVersionString"),
        "build": info.get("CFBundleVersion"),
        "label": info.get("CFBundleDisplayName") or info.get("CFBundleName"),
        "deployment_target": plist.get("deployment_target"),
        "build_sdk": plist.get("sdk_version"),
        "xcode": plist.get("xcode"),
        "simulator_build": plist.get("simulator_build"),
        "min_os": head["min_os"] if head else None,
        "sdk": head["sdk"] if head else None,
        "binary_platform": head["platform"] if head else None,
        "arches": head["arches"] if head else [],
        "encrypted": encrypted,
        "stack": summarize(signals, "ios"),
        "signals": signals,
        "frameworks": list(frameworks.values()),
        "linked": [d for d in dylibs if not d.startswith(("/usr/lib/", "@rpath/" + (exe or "\0")))],
        "storage": storage,
        "notes": notes,
    }
