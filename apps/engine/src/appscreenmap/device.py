"""What a crawl ran on: device type, model, OS build, display and the settings that change what an app shows.

Pure parsing, so it is testable without a device. The driver runs `getprop` and `PROBE` (one shell call
each) and hands the output to `build_info`. Nothing personal is read: no user-set device name, accounts,
IMEI or network names. `run.device` is stored in the run, so it travels with it when shared.
"""

from __future__ import annotations

import re

# section → shell command. Joined into one script so the probe costs one adb round trip.
_PROBE_CMDS = {
    "wm_size": "wm size",
    "wm_density": "wm density",
    "font_scale": "settings get system font_scale",
    "features": "pm list features",
    "meminfo": "grep MemTotal /proc/meminfo",
    "df": "df -k /data | tail -1",
    "kernel": "uname -r",
    "night": "cmd uimode night",
    "navigation_mode": "settings get secure navigation_mode",
    "a11y_services": "settings get secure enabled_accessibility_services",
    "bold_text": "settings get secure font_weight_adjustment",
    "high_contrast": "settings get secure high_text_contrast_enabled",
    "inversion": "settings get secure accessibility_display_inversion_enabled",
    "animator_scale": "settings get global animator_duration_scale",
    "low_power": "settings get global low_power",
    "airplane": "settings get global airplane_mode_on",
    "battery": "dumpsys battery",
    "webview": "dumpsys webviewupdate | grep -m1 'Current WebView package'",
    "gms": "dumpsys package com.google.android.gms | grep -m1 versionName",
}
_SEP = "@@ASM@@"
PROBE = "; ".join(f"echo {_SEP}{name}; {cmd} 2>/dev/null" for name, cmd in _PROBE_CMDS.items())

_PROP_RE = re.compile(r"^\[([^\]]+)\]: \[(.*)\]$", re.MULTILINE)
_NULL = {"", "null", "None"}
_EMULATOR_HW = {"ranchu", "goldfish", "vbox86", "ttVM_x86"}
_NAV_MODES = {"0": "3-button", "1": "2-button", "2": "gesture"}
_TALKBACK = ("talkback", "TalkBackService")


def parse_getprop(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in _PROP_RE.finditer(text)}


def parse_probe(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in text.split(_SEP)[1:]:
        name, _, body = chunk.partition("\n")
        out[name.strip()] = body.strip()
    return out


def _first(props: dict, *keys: str) -> str | None:
    for k in keys:
        if (v := props.get(k, "").strip()) and v not in _NULL:
            return v
    return None


def _int(s: str | None) -> int | None:
    try:
        return int(s) if s not in (None, *_NULL) else None
    except ValueError:
        return None


def _float(s: str | None) -> float | None:
    try:
        return float(s) if s not in (None, *_NULL) else None
    except ValueError:
        return None


def _flag(s: str | None) -> bool | None:
    v = _int(s)
    return None if v is None else v != 0


def _pair(text: str, label: str) -> tuple[int, int] | None:
    m = re.search(rf"{label} size: (\d+)x(\d+)", text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _density(text: str, label: str) -> int | None:
    m = re.search(rf"{label} density: (\d+)", text)
    return int(m.group(1)) if m else None


def device_type(props: dict, serial: str | None = None) -> str:
    """'emulator' (AVD, Genymotion and other virtual devices) or 'physical'."""
    if "1" in (props.get("ro.kernel.qemu"), props.get("ro.boot.qemu")):
        return "emulator"
    if props.get("ro.hardware") in _EMULATOR_HW or props.get("ro.genymotion.version"):
        return "emulator"
    model = props.get("ro.product.model", "")
    fingerprint = props.get("ro.build.fingerprint", "")
    if model.startswith(("sdk_", "Android SDK built for")) or fingerprint.startswith(
        ("generic", "google/sdk_")
    ):
        return "emulator"
    if (serial or "").startswith("emulator-"):
        return "emulator"
    return "physical"


def os_skin(props: dict) -> str | None:
    """The vendor layer on top of Android (One UI, HyperOS, MIUI, ColorOS, …); None on stock Android."""
    if v := _int(props.get("ro.build.version.oneui")):  # 60100 → 6.1, 50101 → 5.1.1
        major, minor, patch = v // 10000, (v // 100) % 100, v % 100
        return f"One UI {major}.{minor}" + (f".{patch}" if patch else "")
    if v := _first(props, "ro.mi.os.version.name"):
        return f"HyperOS {v.removeprefix('OS')}"
    if v := _first(props, "ro.miui.ui.version.name"):
        return f"MIUI {v.lstrip('V')}"
    if v := _first(props, "hw_sc.build.platform.version"):
        return f"HarmonyOS {v}"
    if v := _first(props, "ro.build.version.emui"):
        return f"EMUI {v.removeprefix('EmotionUI_')}"
    if v := _first(props, "ro.build.version.realmeui"):
        return f"realme UI {v.lstrip('V')}"
    if v := _first(props, "ro.oxygen.version"):
        return f"OxygenOS {v}"
    if v := _first(props, "ro.build.version.oplusrom", "ro.build.version.opporom"):
        brand = props.get("ro.product.brand", "").lower()
        return f"{'OxygenOS' if brand == 'oneplus' else 'ColorOS'} {v.lstrip('V')}"
    if v := _first(props, "ro.vivo.os.version"):
        return f"{_first(props, 'ro.vivo.os.name') or 'Funtouch OS'} {v}"
    return None


def _form_factor(props: dict, features: set[str], smallest_dp: int | None) -> str:
    chars = props.get("ro.build.characteristics", "")
    if "android.hardware.type.watch" in features or "watch" in chars:
        return "watch"
    if "android.hardware.type.automotive" in features or "automotive" in chars:
        return "automotive"
    if features & {"android.hardware.type.television", "android.software.leanback"} or "tv" in chars:
        return "tv"
    if "android.hardware.sensor.hinge_angle" in features:
        return "foldable"
    if "tablet" in chars or (smallest_dp or 0) >= 600:
        return "tablet"
    return "phone"


def window_class(width_dp: int | None) -> str | None:
    """Material window size class for the current width: compact < 600 dp ≤ medium < 840 dp ≤ expanded."""
    if width_dp is None:
        return None
    return "compact" if width_dp < 600 else "medium" if width_dp < 840 else "expanded"


def _display_name(dtype: str, props: dict, avd: str | None) -> str:
    manufacturer = _first(props, "ro.product.manufacturer") or ""
    model = _first(props, "ro.product.model") or "unknown"
    if dtype == "emulator":
        host = "Genymotion" if props.get("ro.genymotion.version") else "Android Emulator"
        return f"{host} ({avd})" if avd else host
    name = (
        _first(
            props,
            "ro.product.marketname",
            "ro.product.vendor.marketname",
            "ro.product.odm.marketname",
            "ro.config.marketing_name",
        )
        or model
    )
    makers = tuple(m.lower() for m in (manufacturer, _first(props, "ro.product.brand")) if m)
    if makers and not name.lower().startswith(makers):
        name = f"{manufacturer[:1].upper()}{manufacturer[1:]} {name}"
    return name


def _battery(text: str) -> dict:
    level = re.search(r"^\s*level: (\d+)", text, re.MULTILINE)
    plugged = re.findall(r"^\s*(?:AC|USB|Wireless|Dock) powered: (true|false)", text, re.MULTILINE)
    return {
        "battery": int(level.group(1)) if level else None,
        "charging": ("true" in plugged) if plugged else None,
    }


def _webview(text: str) -> str | None:
    m = re.findall(r"\(([\w.]+), ([^)]+)\)", text)  # "(name, version): (com.google.android.webview, 141.0…)"
    return f"{m[-1][0]} {m[-1][1]}" if m and m[-1][0] != "name" else None


def build_info(serial: str | None, props: dict, probe: dict, avd: str | None = None) -> dict:
    """Everything `run.device` holds. Keeps the original flat keys; new detail sits in groups."""
    dtype = device_type(props, serial)
    avd = avd or _first(props, "ro.boot.qemu.avd_name", "ro.kernel.qemu.avd_name")
    wm_size, wm_density = probe.get("wm_size", ""), probe.get("wm_density", "")
    physical = _pair(wm_size, "Physical")
    override = _pair(wm_size, "Override")
    width, height = override or physical or (None, None)
    density = _density(wm_density, "Override") or _density(wm_density, "Physical")
    scale = (density or 160) / 160
    width_dp = round(width / scale) if width else None
    height_dp = round(height / scale) if height else None
    smallest_dp = min(width_dp, height_dp) if width_dp and height_dp else None
    features = {
        line.removeprefix("feature:").split("=")[0].strip()
        for line in probe.get("features", "").splitlines()
        if line.startswith("feature:")
    }
    mem = re.search(r"(\d+)", probe.get("meminfo", ""))
    df = probe.get("df", "").split()
    services = [s for s in (probe.get("a11y_services") or "").split(":") if s and s not in _NULL]
    night = probe.get("night", "").lower()
    soc = " ".join(p for p in (_first(props, "ro.soc.manufacturer"), _first(props, "ro.soc.model")) if p)
    abis = [a for a in (props.get("ro.product.cpu.abilist") or "").split(",") if a]
    sdk = _first(props, "ro.build.version.sdk")
    codename = _first(props, "ro.build.version.codename")

    return {
        # original keys (schema 1, keep)
        "serial": serial,
        "model": _first(props, "ro.product.model"),
        "manufacturer": _first(props, "ro.product.manufacturer"),
        "android": _first(props, "ro.build.version.release"),
        "sdk": sdk,
        "width": width,
        "height": height,
        "density": density,
        "font_scale": _float(probe.get("font_scale")) or 1.0,
        # identity
        "type": dtype,
        "name": _display_name(dtype, props, avd),
        "brand": _first(props, "ro.product.brand"),
        "codename": _first(props, "ro.product.device"),
        "product": _first(props, "ro.product.name"),
        "avd": avd if dtype == "emulator" else None,
        "form_factor": _form_factor(props, features, smallest_dp),
        "connection": "emulator"
        if (serial or "").startswith("emulator-")
        else "wifi"
        if ":" in (serial or "")
        else "usb",
        "os": {
            "release": _first(props, "ro.build.version.release"),
            "sdk": _int(sdk),
            "codename": codename,  # "REL" on release builds, a letter on previews
            "preview_sdk": _int(props.get("ro.build.version.preview_sdk")) or None,
            "skin": os_skin(props),
            "security_patch": _first(props, "ro.build.version.security_patch"),
            "build_id": _first(props, "ro.build.id"),
            "incremental": _first(props, "ro.build.version.incremental"),
            "build_type": _first(props, "ro.build.type"),  # user | userdebug | eng
            "build_tags": _first(props, "ro.build.tags"),
            "fingerprint": _first(props, "ro.build.fingerprint"),
            "kernel": probe.get("kernel") or None,
        },
        "hardware": {
            "abi": _first(props, "ro.product.cpu.abi"),
            "abis": abis,
            "soc": soc or _first(props, "ro.hardware.chipname", "ro.board.platform"),
            "hardware": _first(props, "ro.hardware"),
            "ram_mb": int(mem.group(1)) // 1024 if mem else None,
            "storage_free_mb": int(df[3]) // 1024 if len(df) >= 4 and df[3].isdigit() else None,
        },
        "display": {
            "width": width,
            "height": height,
            "physical_width": physical[0] if physical else None,
            "physical_height": physical[1] if physical else None,
            "density": density,
            "physical_density": _density(wm_density, "Physical"),
            "width_dp": width_dp,
            "height_dp": height_dp,
            "smallest_width_dp": smallest_dp,
            "window_class": window_class(width_dp),
        },
        "settings": {
            "locale": _first(props, "persist.sys.locale", "ro.product.locale"),
            "timezone": _first(props, "persist.sys.timezone"),
            "dark_mode": True if "yes" in night else False if "no" in night else None,  # None = auto/custom
            "font_scale": _float(probe.get("font_scale")) or 1.0,
            "bold_text": (v > 0) if (v := _int(probe.get("bold_text"))) is not None else None,
            "high_contrast_text": _flag(probe.get("high_contrast")),
            "color_inversion": _flag(probe.get("inversion")),
            "animator_scale": _float(probe.get("animator_scale")),  # before the crawl turns animations off
            "navigation": _NAV_MODES.get(probe.get("navigation_mode", "")),
            "talkback": any(t in s for s in services for t in _TALKBACK),
            "accessibility_services": services,
            "power_saver": _flag(probe.get("low_power")),
            "airplane_mode": _flag(probe.get("airplane")),
            **_battery(probe.get("battery", "")),
        },
        "software": {
            "webview": _webview(probe.get("webview", "")),
            "play_services": (
                m.group(1) if (m := re.search(r"versionName=(\S+)", probe.get("gms", ""))) else None
            ),
        },
    }


# ── for reports ──────────────────────────────────────────────────────────────


def describe(dev: dict) -> str:
    """One line: 'Samsung Galaxy S23 (SM-S911B) · physical phone · Android 14 (SDK 34), One UI 6.1'."""
    name = (
        dev.get("name") or " ".join(p for p in (dev.get("manufacturer"), dev.get("model")) if p) or "unknown"
    )
    model = dev.get("model")
    if model and model not in name:
        name += f" ({model})"
    kind = " ".join(p for p in (dev.get("type"), dev.get("form_factor")) if p)
    os_ = f"Android {dev.get('android', '?')} (SDK {dev.get('sdk', '?')})"
    if skin := (dev.get("os") or {}).get("skin"):
        os_ += f", {skin}"
    return " · ".join(p for p in (name, kind, os_) if p)


def rows(dev: dict) -> list[tuple[str, str]]:
    """Label/value rows for a device section; skips what an old run didn't record."""
    os_, hw = dev.get("os") or {}, dev.get("hardware") or {}
    disp, st, sw = dev.get("display") or {}, dev.get("settings") or {}, dev.get("software") or {}

    def on(v):
        return None if v is None else "on" if v else "off"

    out = [
        ("Device", dev.get("name") or f"{dev.get('manufacturer', '')} {dev.get('model', '')}".strip()),
        ("Model", " / ".join(p for p in (dev.get("brand"), dev.get("model"), dev.get("codename")) if p)),
        ("Type", " ".join(p for p in (dev.get("type"), dev.get("form_factor")) if p)),
        ("Connection", dev.get("connection")),
        (
            "Android",
            f"{dev.get('android', '?')} (SDK {dev.get('sdk', '?')})"
            + (f", {os_['skin']}" if os_.get("skin") else ""),
        ),
        ("Security patch", os_.get("security_patch")),
        ("Build", " ".join(p for p in (os_.get("build_id"), os_.get("build_type")) if p)),
        ("CPU", " · ".join(p for p in (hw.get("soc"), hw.get("abi")) if p)),
        ("RAM", f"{hw['ram_mb'] / 1024:.1f} GB" if hw.get("ram_mb") else None),
        (
            "Screen",
            f"{dev.get('width')}×{dev.get('height')} px, {dev.get('density') or '?'} dpi"
            + (
                f", {disp['width_dp']}×{disp['height_dp']} dp ({disp['window_class']})"
                if disp.get("width_dp")
                else ""
            ),
        ),
        (
            "Font scale",
            f"{dev['font_scale']:g}" + (", bold text" if st.get("bold_text") else "")
            if dev.get("font_scale")
            else "1.0 (assumed)",
        ),
        ("Locale", " · ".join(p for p in (st.get("locale"), st.get("timezone")) if p)),
        ("Dark mode", on(st.get("dark_mode"))),
        ("Navigation", st.get("navigation")),
        ("TalkBack", on(st.get("talkback")) if "talkback" in st else None),
        ("Power saver", on(st.get("power_saver"))),
        (
            "Battery",
            f"{st['battery']}%" + (" charging" if st.get("charging") else "")
            if st.get("battery") is not None
            else None,
        ),
        ("WebView", sw.get("webview")),
        ("Play services", sw.get("play_services")),
    ]
    return [(k, str(v)) for k, v in out if v not in (None, "", "?")]


def caveats(dev: dict) -> list[str]:
    """Device conditions that change what a run's numbers or screenshots mean."""
    os_, st = dev.get("os") or {}, dev.get("settings") or {}
    out = []
    if dev.get("type") == "emulator":
        out.append("emulator: load times and jank are not representative of real devices")
    if st.get("power_saver"):
        out.append("power saver was on: the CPU is throttled and some animations are cut")
    if (b := st.get("battery")) is not None and b < 15 and not st.get("charging"):
        out.append(f"battery at {b}% and not charging: the device may throttle or kill background work")
    if st.get("talkback"):
        out.append("TalkBack was running: taps and focus behave differently from a sighted user")
    if (fs := dev.get("font_scale")) and fs != 1.0:
        out.append(f"font scale {fs:g}: screenshots and layout show enlarged text")
    if st.get("dark_mode"):
        out.append("dark mode was on: contrast findings apply to the dark theme")
    if st.get("airplane_mode"):
        out.append("airplane mode was on: screens that need the network show offline states")
    if os_.get("codename") not in (None, "REL"):
        out.append(f"Android preview build ({os_['codename']}): behaviour may change before release")
    if (fs := (dev.get("hardware") or {}).get("storage_free_mb")) is not None and fs < 500:
        out.append(f"only {fs} MB free on /data: installs and caches may fail")
    return out
