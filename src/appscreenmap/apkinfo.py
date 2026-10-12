"""Static facts about an APK via aapt2: package, version, label, launch activity, declared activities."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


def find_aapt2() -> str | None:
    if path := shutil.which("aapt2"):
        return path
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if root := os.environ.get(env):
            break
    else:
        root = str(Path.home() / "Library/Android/sdk")
        if not Path(root).exists():
            root = str(Path.home() / "Android/Sdk")
    build_tools = Path(root) / "build-tools"
    if not build_tools.is_dir():
        return None

    def version_key(p: Path):
        return [int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", p.name)]

    for d in sorted(build_tools.iterdir(), key=version_key, reverse=True):
        if (d / "aapt2").exists():
            return str(d / "aapt2")
    return None


def apk_info(apk: str | Path) -> dict:
    """Best effort; returns {} if aapt2 is unavailable or fails."""
    aapt2 = find_aapt2()
    if not aapt2:
        return {}
    info: dict = {}
    try:
        badging = subprocess.run(
            [aapt2, "dump", "badging", str(apk)], check=False, capture_output=True, text=True, timeout=60
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if m := re.search(r"package: name='([^']+)'.*?versionName='([^']*)'", badging):
        info["package"], info["version"] = m.group(1), m.group(2)
    if m := re.search(r"application-label:'([^']*)'", badging):
        info["label"] = m.group(1)
    if m := re.search(r"launchable-activity: name='([^']+)'", badging):
        info["launch_activity"] = m.group(1)
    acts = manifest_activities(apk, aapt2)
    info["activities"] = sorted({a["name"] for a in acts})
    info["orientation_locked"] = {
        a["name"]: LOCKED_ORIENTATIONS[a["orientation"]]
        for a in acts
        if a["orientation"] in LOCKED_ORIENTATIONS
    }
    return info


# android:screenOrientation values that pin an activity to portrait or landscape (WCAG 1.3.4).
LOCKED_ORIENTATIONS = {
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


def manifest_activities(apk: str | Path, aapt2: str | None = None) -> list[dict]:
    """Activities declared in the manifest: [{"name", "orientation"}] (orientation = int or None)."""
    aapt2 = aapt2 or find_aapt2()
    if not aapt2:
        return []
    try:
        tree = subprocess.run(
            [aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", str(apk)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_manifest_activities(tree)


def parse_manifest_activities(tree: str) -> list[dict]:
    """Parse `aapt2 dump xmltree` output of AndroidManifest.xml."""
    package = re.search(r'A: package="([^"]+)"', tree)
    acts: list[dict] = []
    current: dict | None = None
    for line in tree.splitlines():
        s = line.strip()
        if s.startswith("E: "):
            current = (
                {"name": None, "orientation": None} if re.match(r"E: activity(-alias)?(\s|$)", s) else None
            )
            if current is not None:
                acts.append(current)
            continue
        if current is None:
            continue
        if m := re.search(r':name\(0x01010003\)="([^"]+)"', s):
            name = m.group(1)
            current["name"] = package.group(1) + name if name.startswith(".") and package else name
        elif m := re.search(r":screenOrientation\(0x0101001e\)=(?:\(type 0x10\))?(0x[0-9a-f]+|\d+)", s):
            current["orientation"] = int(m.group(1), 0)
    return [a for a in acts if a["name"]]


def declared_activities(apk: str | Path, aapt2: str | None = None) -> list[str]:
    return sorted({a["name"] for a in manifest_activities(apk, aapt2)})
