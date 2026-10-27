"""What a build declares about sizes: the APK manifest (aapt2 xmltree) or the iOS Info.plist. No device needed."""

from __future__ import annotations

import plistlib
import re
import subprocess
import zipfile
from pathlib import Path

from appscreenmap.drivers.apkinfo import find_aapt2

# android:screenOrientation values (ActivityInfo.SCREEN_ORIENTATION_*) that pin an activity.
LOCKED = {
    0: "landscape",
    1: "portrait",
    6: "sensorLandscape",
    7: "sensorPortrait",
    8: "reverseLandscape",
    9: "reversePortrait",
    11: "userLandscape",
    12: "userPortrait",
    14: "locked",
}
NOSENSOR = 5
# ActivityInfo.CONFIG_*: an activity handling all four isn't recreated on fold, rotate or resize.
SIZE_CHANGES = 0x80 | 0x100 | 0x400 | 0x800  # orientation, screenLayout, screenSize, smallestScreenSize
_ATTR = re.compile(r":(\w+)\(0x[0-9a-f]+\)=(?:\(type 0x[0-9a-f]+\))?(\"[^\"]*\"|\S+)")


def _value(raw: str):
    if raw.startswith('"'):
        return raw.strip('"')
    if raw in ("true", "false"):
        return raw == "true"
    try:
        return int(raw, 0)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


def _flag(v) -> bool | None:
    """aapt2 prints booleans as true/false or as 0x0 / 0xffffffff."""
    if v is None:
        return None
    return bool(v) if isinstance(v, (bool, int)) else str(v).lower() == "true"


OPT_OUT = "android.window.PROPERTY_COMPAT_ALLOW_RESTRICTED_RESIZABILITY"  # Android 16's temporary opt-out


def _opted_out(el: dict) -> bool:
    return any(p.get("name") == OPT_OUT and _flag(p.get("value")) for p in el.get("_props") or [])


def parse_manifest(tree: str) -> dict:
    """Facts from `aapt2 dump xmltree --file AndroidManifest.xml`: SDK, game, and per-activity size attributes."""
    package = m.group(1) if (m := re.search(r'A: package="([^"]+)"', tree)) else None
    facts: dict = {
        "platform": "android",
        "package": package,
        "target_sdk": None,
        "game": False,
        "app": {},
        "activities": [],
        "notes": [],
    }
    current: dict | None = None
    owner: dict | None = None  # the activity or application a <property> belongs to
    for line in tree.splitlines():
        s = line.strip()
        if s.startswith("E: "):
            tag = s[3:].split()[0]
            if tag in ("activity", "activity-alias"):
                current = owner = {"name": None}
                facts["activities"].append(current)
            elif tag == "application":
                current = owner = facts["app"]
            elif tag == "property" and owner is not None:
                current = {}
                owner.setdefault("_props", []).append(current)
            elif tag == "uses-sdk":
                current = {}
                facts["_sdk"] = current
            else:
                current = None
            continue
        if current is None or not (a := _ATTR.search(s)):
            continue
        current[a.group(1)] = _value(a.group(2))
    sdk = facts.pop("_sdk", {})
    facts["target_sdk"] = (
        sdk.get("targetSdkVersion") if isinstance(sdk.get("targetSdkVersion"), int) else None
    )
    app = facts["app"]
    facts["game"] = app.get("appCategory") == 0 or _flag(app.get("isGame")) is True
    facts["opt_out"] = _opted_out(app)
    acts = []
    for a in facts["activities"]:
        name = a.get("name")
        if not isinstance(name, str):
            continue
        if name.startswith(".") and package:
            name = package + name
        acts.append(
            {
                "name": name,
                "orientation": a.get("screenOrientation")
                if isinstance(a.get("screenOrientation"), int)
                else None,
                "resizeable": _flag(a.get("resizeableActivity", app.get("resizeableActivity"))),
                "min_aspect": a.get("minAspectRatio"),
                "max_aspect": a.get("maxAspectRatio"),
                "config_changes": a.get("configChanges") if isinstance(a.get("configChanges"), int) else 0,
                "opt_out": _opted_out(a),
                "alias": "targetActivity" in a,
            }
        )
    facts["activities"] = acts
    return facts


def android_facts(apk: str | Path) -> dict:
    aapt2 = find_aapt2()
    if not aapt2:
        return {
            "platform": "android",
            "notes": ["aapt2 not found, so the manifest could not be read (install Android build-tools)."],
        }
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
        return {"platform": "android", "notes": ["aapt2 could not read the manifest."]}
    return parse_manifest(tree)


def _strings(v) -> list[str]:
    return [str(x) for x in v] if isinstance(v, list) else []


def parse_plist(info: dict) -> dict:
    """Only the keys the rules read; a malformed value reads as absent, never as an error."""
    info = info if isinstance(info, dict) else {}
    xcode = str(info.get("DTXcode") or "")  # "2601" = Xcode 26.0.1
    return {
        "platform": "ios",
        "bundle_id": info.get("CFBundleIdentifier"),
        "requires_fullscreen": info.get("UIRequiresFullScreen") is True,
        "scenes": isinstance(info.get("UIApplicationSceneManifest"), dict),
        "device_family": [int(x) for x in _strings(info.get("UIDeviceFamily")) if x.isdigit()],
        "orientations": _strings(info.get("UISupportedInterfaceOrientations")),
        "orientations_ipad": _strings(info.get("UISupportedInterfaceOrientations~ipad")),
        "xcode_major": int(xcode[:2]) if re.fullmatch(r"\d{4}", xcode) else None,
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
    return parse_plist(info)
