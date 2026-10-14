"""Build facts: the SDK levels an APK or an iOS app was built with (aapt2 manifest, Info.plist). Stdlib only."""

from __future__ import annotations

import plistlib
import re
import subprocess
import zipfile
from pathlib import Path

from appscreenmap.drivers.apkinfo import find_aapt2

_NUM = r"(0x[0-9a-f]+|\d+)"
_ATTR = re.compile(r"^\s*A: (?:[^\s=]*:)?(\w+)(?:\(0x[0-9a-f]+\))?=(.*)$")
_ELEM = re.compile(r"^\s*E: (\S+)")


def _int(raw: str) -> int | None:
    raw = raw.strip().strip('"')
    if m := re.match(rf"^{_NUM}(?:\s|\(|$)", raw):
        return int(m.group(1), 0)
    return None


def parse_android_sdk(tree: str) -> dict:
    """minSdk / targetSdk / compileSdk from `aapt2 dump xmltree` of AndroidManifest.xml.

    compileSdk is the manifest's `compileSdkVersion` (AGP writes it; falls back to `platformBuildVersionCode`).
    A missing value stays None: it is reported as unknown, never guessed.
    """
    out: dict = {"package": None, "min_sdk": None, "target_sdk": None, "compile_sdk": None}
    tag = None
    platform_build = None
    for line in tree.splitlines():
        if e := _ELEM.match(line):
            tag = e.group(1)
            continue
        a = _ATTR.match(line)
        if not a:
            continue
        key, val = a.group(1), a.group(2)
        if tag == "manifest":
            if key == "package":
                out["package"] = val.strip().strip('"').split('"')[0]
            elif key == "compileSdkVersion":
                out["compile_sdk"] = _int(val)
            elif key == "platformBuildVersionCode":
                platform_build = _int(val)
        elif tag == "uses-sdk":
            if key == "minSdkVersion":
                out["min_sdk"] = _int(val)
            elif key == "targetSdkVersion":
                out["target_sdk"] = _int(val)
    if out["compile_sdk"] is None:
        out["compile_sdk"] = platform_build
    return out


def android_facts(apk: str | Path) -> dict:
    """{"platform": "android", min_sdk, target_sdk, compile_sdk, package, "notes": [...]}."""
    facts: dict = {"platform": "android", "notes": []}
    aapt2 = find_aapt2()
    if not aapt2:
        facts["notes"].append(
            "aapt2 not found, so the SDK levels could not be read (install Android build-tools)."
        )
        return facts
    try:
        tree = subprocess.run(
            [aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", str(apk)],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        tree = ""
    if not tree:
        facts["notes"].append("aapt2 could not read the manifest, so the SDK levels could not be read.")
        return facts
    facts.update(parse_android_sdk(tree))
    if facts["compile_sdk"] is None:
        facts["notes"].append(
            "The manifest carries no compileSdkVersion (AGP omits it in some setups), so the build SDK is unknown."
        )
    return facts


def _major(version: str | None) -> int | None:
    if m := re.match(r"(\d+)", version or ""):
        return int(m.group(1))
    return None


def parse_ios_plist(info: dict) -> dict:
    """Build facts from an Info.plist dict. The DT* keys are written by Xcode at build time."""
    sdk_name = info.get("DTSDKName") or ""  # "iphoneos26.0", "iphonesimulator26.0"
    sdk_version = re.search(r"(\d+(?:\.\d+)*)$", sdk_name)
    xcode = str(info.get("DTXcode") or "")  # "2601" = Xcode 26.0.1
    xcode_version = None
    if re.fullmatch(r"\d{4}", xcode):
        xcode_version = f"{int(xcode[:2])}.{int(xcode[2])}" + (f".{int(xcode[3])}" if xcode[3] != "0" else "")
    return {
        "platform": "ios",
        "bundle_id": info.get("CFBundleIdentifier"),
        "sdk_name": sdk_name or None,
        "sdk_version": (sdk_version.group(1) if sdk_version else None) or info.get("DTPlatformVersion"),
        "sdk_major": _major((sdk_version.group(1) if sdk_version else None) or info.get("DTPlatformVersion")),
        "xcode": xcode_version,
        "deployment_target": info.get("MinimumOSVersion"),
        "deployment_major": _major(info.get("MinimumOSVersion")),
        "simulator_build": "simulator" in sdk_name,
        "notes": [],
    }


def ios_facts(app: str | Path) -> dict:
    """Read Info.plist from an `.app` folder or an `.ipa`."""
    app = Path(app)
    try:
        if app.is_dir():
            info = plistlib.loads((app / "Info.plist").read_bytes())
        else:
            with zipfile.ZipFile(app) as z:
                name = next(n for n in z.namelist() if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", n))
                info = plistlib.loads(z.read(name))
    except (OSError, StopIteration, zipfile.BadZipFile, plistlib.InvalidFileException, ValueError) as e:
        return {
            "platform": "ios",
            "notes": [f"Could not read Info.plist from {app}: {e or type(e).__name__}."],
        }
    facts = parse_ios_plist(info)
    if facts["sdk_major"] is None:
        facts["notes"].append(
            "Info.plist has no DTSDKName/DTPlatformVersion (the build was not made by Xcode or was re-signed "
            "without them), so the build SDK is unknown."
        )
    return facts
