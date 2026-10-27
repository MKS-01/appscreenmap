"""Static fingerprints of an installed app's APKs (base plus splits, as pulled from the device)."""

from __future__ import annotations

import json
import re
import subprocess
import zipfile
from functools import cache
from pathlib import Path

from appscreenmap.drivers.apkinfo import find_aapt2
from appscreenmap.store.facts import parse_android_sdk

from .detect import detect, summarize
from .elf import check_16k
from .storage import detect_storage

LIBCHECKER = Path(__file__).with_name("libchecker.json")
_MAX_DEX = 64 * 1024 * 1024
_DEX = re.compile(r"^classes\d*\.dex$")
_COMPONENT = re.compile(r"E: (activity|activity-alias|service|receiver|provider)(\s|$)")
_NAME = re.compile(r':name\(0x01010003\)="([^"]+)"')


@cache
def libchecker() -> dict:
    return json.loads(LIBCHECKER.read_text())


def parse_components(tree: str) -> list[str]:
    """Activity, service, receiver and provider class names from `aapt2 dump xmltree` of the manifest."""
    package = re.search(r'A: package="([^"]+)"', tree)
    names, want = [], False
    for line in tree.splitlines():
        s = line.strip()
        if s.startswith("E: "):
            want = bool(_COMPONENT.match(s))
            continue
        if want and (m := _NAME.search(s)):
            name = m.group(1)
            names.append(package.group(1) + name if name.startswith(".") and package else name)
            want = False
    return sorted(set(names))


def _manifest_tree(apk: Path) -> str:
    aapt2 = find_aapt2()
    if not aapt2:
        return ""
    try:
        return subprocess.run(
            [aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", str(apk)],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _version_name(entry: str) -> str:
    """META-INF/androidx.compose.ui_ui.version → androidx.compose.ui:ui (the Maven group:artifact)."""
    stem = entry.removeprefix("META-INF/").removesuffix(".version")
    group, _, artifact = stem.partition("_")
    return f"{group}:{artifact}" if artifact else stem


def fingerprint(apks: list[Path]) -> dict:
    """Everything the APKs show without running the app. The first APK is the base."""
    libs: dict[str, set[str]] = {}
    paths: list[str] = []
    dex = bytearray()
    libraries: dict[str, str] = {}
    page_16k: list[dict] = []
    notes: list[str] = []
    for apk in apks:
        try:
            z = zipfile.ZipFile(apk)
        except (OSError, zipfile.BadZipFile) as e:
            notes.append(f"{apk.name} could not be read: {e}.")
            continue
        with z:
            for info in z.infolist():
                name = info.filename
                paths.append(name)
                parts = name.split("/")
                if len(parts) == 3 and parts[0] == "lib" and parts[2].endswith(".so"):
                    libs.setdefault(parts[2], set()).add(parts[1])
                elif _DEX.match(name) and info.file_size <= _MAX_DEX:
                    dex += z.read(info)
                elif name.startswith("META-INF/") and name.endswith(".version") and info.file_size < 200:
                    libraries[_version_name(name)] = z.read(info).decode(errors="replace").strip()
            page_16k += check_16k(z)
    rules = libchecker()
    tree = _manifest_tree(apks[0]) if apks else ""
    if not tree:
        notes.append(
            "aapt2 could not read the manifest (install Android build-tools), so compileSdk and components are unknown."
        )
    sdk = parse_android_sdk(tree) if tree else {}
    code = bytes(dex)
    signals = detect(set(libs), paths, code)
    return {
        "apks": [a.name for a in apks],
        "compile_sdk": sdk.get("compile_sdk"),
        "manifest_min_sdk": sdk.get("min_sdk"),
        "manifest_target_sdk": sdk.get("target_sdk"),
        "abis": sorted({abi for abis in libs.values() for abi in abis}),
        "stack": summarize(signals),
        "signals": signals,
        "native_libs": [
            {
                "name": n,
                "abis": sorted(a),
                **({"library": rules["native"][n]} if n in rules["native"] else {}),
            }
            for n, a in sorted(libs.items())
        ],
        "components": [
            {"name": c, "library": rules["components"][c]}
            for c in parse_components(tree)
            if c in rules["components"]
        ],
        "libraries": [{"name": k, "version": v} for k, v in sorted(libraries.items())],
        "storage": detect_storage(set(libs), paths, code),
        "page_16k": page_16k,
        "notes": notes,
    }
