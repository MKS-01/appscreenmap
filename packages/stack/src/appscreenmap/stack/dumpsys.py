"""What the device's package manager knows about an installed app: `adb shell dumpsys package <pkg>`."""

from __future__ import annotations

import re

_INT_KEYS = {"versionCode": "version_code", "minSdk": "min_sdk", "targetSdk": "target_sdk"}
_STR_KEYS = {
    "versionName": "version",
    "primaryCpuAbi": "primary_abi",
    "installerPackageName": "installer",
    "firstInstallTime": "first_install",
    "lastUpdateTime": "last_update",
    "apkSigningVersion": "signing_version",
    "extractNativeLibs": "extract_native_libs",
}


def parse_dumpsys_package(text: str, package: str) -> dict:
    """Facts from the first `Package [<package>]` block; a value dumpsys doesn't print stays absent."""
    out: dict = {}
    block, indent = False, 0
    for line in text.splitlines():
        if not line.strip():
            continue
        lead = len(line) - len(line.lstrip())
        if line.strip().startswith(f"Package [{package}]"):
            if block:
                break  # a second block (hidden system package, other user): the first is the installed one
            block, indent = True, lead
            continue
        if not block:
            continue
        if lead <= indent:
            break
        s = line.strip()
        for key, name in _INT_KEYS.items():
            if m := re.search(rf"(?:^|\s){key}=(\d+)", s):
                out.setdefault(name, int(m.group(1)))
        for key, name in _STR_KEYS.items():
            if m := re.match(rf"{key}=(.*)$", s):
                val = m.group(1).strip()
                if val and val != "null":
                    out.setdefault(name, val)
        if m := re.match(r"(?:pkg)?[Ff]lags=\[(.*)\]", s):
            out.setdefault("flags", m.group(1).split())
        elif m := re.match(r"splits=\[(.*)\]", s):
            out.setdefault("splits", [p.strip() for p in m.group(1).split(",") if p.strip()])
    if "signing_version" in out and out["signing_version"].isdigit():
        out["signing_version"] = int(out["signing_version"])
    if "extract_native_libs" in out:
        out["extract_native_libs"] = out["extract_native_libs"] == "true"
    if "flags" in out:
        out["debuggable"] = "DEBUGGABLE" in out["flags"]
    return out
