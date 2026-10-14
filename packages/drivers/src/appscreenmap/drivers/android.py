"""Android driver: drives a device or emulator over adb (uiautomator dumps, input, dumpsys)."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from .base import DriverError, Snapshot
from .device import PROBE, build_info, parse_getprop, parse_probe
from .dumpsys import TOTAL_FRAMES_RE, parse_am_start, parse_framestats, parse_gfx_summary

_DUMP_PATH = "/sdcard/appscreenmap_dump.xml"
_MARK = "__APPSCREENMAP__"
_ACTIVITY_RE = re.compile(r"ActivityRecord\{\S+ u\d+ ([\w.]+)/([\w.$]+)")


class AdbDriver:
    def __init__(self, serial: str | None = None, adb: str | None = None):
        self.adb_path = adb or shutil.which("adb")
        if not self.adb_path:
            raise DriverError("adb not found on PATH. Install Android platform-tools.")
        self.serial = serial or self._pick_device()
        self._size: tuple[int, int] | None = None

    # ── low level ────────────────────────────────────────────────────────────
    def _run(self, args: list[str], timeout: float = 60, binary: bool = False, check: bool = True):
        cmd = [self.adb_path, *(["-s", self.serial] if getattr(self, "serial", None) else []), *args]
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise DriverError(f"adb timed out: {' '.join(args)}") from e
        if check and proc.returncode != 0:
            err = proc.stderr.decode(errors="replace").strip() or proc.stdout.decode(errors="replace").strip()
            raise DriverError(f"adb {' '.join(args)} failed: {err}")
        return proc.stdout if binary else proc.stdout.decode(errors="replace")

    def shell(self, cmd: str, timeout: float = 30, check: bool = False) -> str:
        return self._run(["shell", cmd], timeout=timeout, check=check)

    @classmethod
    def list_devices(cls, adb: str | None = None) -> list[tuple[str, str]]:
        path = adb or shutil.which("adb")
        if not path:
            return []
        out = subprocess.run([path, "devices"], check=False, capture_output=True, text=True).stdout
        rows = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                rows.append((parts[0], parts[1]))
        return rows

    def _pick_device(self) -> str:
        ready = [s for s, state in self.list_devices(self.adb_path) if state == "device"]
        if not ready:
            raise DriverError("No device/emulator connected. Start one and check `adb devices`.")
        if len(ready) > 1:
            raise DriverError(f"Several devices connected ({', '.join(ready)}); pass --serial.")
        return ready[0]

    # ── device info ──────────────────────────────────────────────────────────
    def prop(self, name: str) -> str:
        return self.shell(f"getprop {name}").strip()

    def screen_size(self) -> tuple[int, int]:
        if self._size is None:
            out = self.shell("wm size")
            m = re.findall(r"(\d+)x(\d+)", out)
            if not m:
                raise DriverError(f"Could not read screen size: {out!r}")
            w, h = m[-1]  # "Override size" (last) wins over "Physical size"
            self._size = (int(w), int(h))
        return self._size

    def info(self) -> dict:
        """Device facts for `run.device` (see `device.build_info`): two shell calls plus the AVD name."""
        props = parse_getprop(self.shell("getprop"))
        probe = parse_probe(self.shell(PROBE, timeout=60))
        avd = None
        if self.serial.startswith("emulator-") and "ro.boot.qemu.avd_name" not in props:
            out = self._run(["emu", "avd", "name"], timeout=10, check=False).strip().splitlines()
            avd = out[0].strip() if out and out[0].strip() != "OK" else None
        info = build_info(self.serial, props, probe, avd)
        if info["width"] is None:  # wm failed inside the probe; screen_size raises with the reason
            info["width"], info["height"] = self.screen_size()
        return info

    def density(self) -> int | None:
        """Screen density in dpi (px per dp = density / 160). Override wins over physical."""
        m = re.findall(r"density: (\d+)", self.shell("wm density"))
        return int(m[-1]) if m else None

    def get_font_scale(self) -> float:
        try:
            return float(self.shell("settings get system font_scale").strip())
        except ValueError:
            return 1.0

    def set_font_scale(self, scale: float) -> None:
        self.shell(f"settings put system font_scale {scale:g}")

    # ── app management ───────────────────────────────────────────────────────
    def install(self, apk: str | Path, grant: bool = True) -> None:
        args = ["install", "-r", "-t"] + (["-g"] if grant else []) + [str(apk)]
        out = self._run(args, timeout=300)
        if "Success" not in out:
            raise DriverError(f"install failed: {out.strip()}")

    def is_installed(self, package: str) -> bool:
        return f"package:{package}" in self.shell(f"pm list packages {package}").split()

    def resolve_launch_activity(self, package: str) -> str | None:
        out = self.shell(
            f"cmd package resolve-activity --brief -c android.intent.category.LAUNCHER {package}"
        )
        for line in reversed(out.strip().splitlines()):
            if "/" in line:
                pkg, act = line.strip().split("/", 1)
                return pkg + act if act.startswith(".") else act
        return None

    def app_version(self, package: str) -> str | None:
        m = re.search(r"versionName=(\S+)", self.shell(f"dumpsys package {package}"))
        return m.group(1) if m else None

    def apk_path(self, package: str) -> str | None:
        for line in self.shell(f"pm path {package}").splitlines():
            if line.startswith("package:") and line.endswith("base.apk"):
                return line[len("package:") :].strip()
        return None

    def pull(self, remote: str, local: str | Path) -> None:
        self._run(["pull", remote, str(local)], timeout=300)

    def run_as(self, package: str, command: str) -> str | None:
        """Run a shell command in an app's data folder: `run-as` for a debuggable build, else `su 0` on a rooted
        emulator. None when neither can enter it."""
        for cmd in (
            f'run-as {package} sh -c "{command}"',
            f'su 0 sh -c "cd /data/data/{package} && {command}"',
        ):
            out = self.shell(f"{cmd} 2>&1", timeout=60)
            if not re.match(r"\s*(run-as:|su:|/system/bin/sh: su:)|.*inaccessible or not found", out):
                return out
        return None

    def launch(self, package: str, activity: str | None) -> dict:
        """Start the app. Returns `am start -W` timing ({TotalTime, WaitTime, LaunchState}) when known."""
        if activity:
            return parse_am_start(self.shell(f"am start -W -n {package}/{activity}", timeout=60))
        self.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1", timeout=60)
        return {}

    # ── rendering stats (navigation performance) ─────────────────────────────
    def gfx_reset(self, package: str) -> None:
        self.shell(f"dumpsys gfxinfo {package} reset >/dev/null")

    def frames_rendered(self, package: str) -> int | None:
        m = TOTAL_FRAMES_RE.search(
            self.shell(f"dumpsys gfxinfo {package} 2>/dev/null | grep -m1 'Total frames rendered'")
        )
        return int(m.group(1)) if m else None

    def gfx_summary(self, package: str) -> dict:
        return parse_gfx_summary(self.shell(f"dumpsys gfxinfo {package}"))

    def gfx_framestats(self, package: str) -> list[dict]:
        return parse_framestats(self.shell(f"dumpsys gfxinfo {package} framestats", timeout=30))

    def force_stop(self, package: str) -> None:
        self.shell(f"am force-stop {package}")

    def clear_data(self, package: str) -> None:
        self.shell(f"pm clear {package}")

    def grant_all(self, package: str) -> None:
        """Best effort: grant every runtime permission the app requests."""
        dump = self.shell(f"dumpsys package {package}")
        for perm in sorted(set(re.findall(r"(android\.permission\.[A-Z_]+): granted=false", dump))):
            self.shell(f"pm grant {package} {perm}")

    # ── observation ──────────────────────────────────────────────────────────
    def snapshot(self, retries: int = 3) -> Snapshot:
        """Dump the UI hierarchy and read the resumed activity in one round trip."""
        cmd = (
            f"rm -f {_DUMP_PATH}; uiautomator dump {_DUMP_PATH} >/dev/null 2>&1; cat {_DUMP_PATH}; "
            f"echo; echo {_MARK}; dumpsys activity activities | grep -m1 topResumedActivity"
        )
        last = ""
        for attempt in range(retries):
            out = self.shell(cmd, timeout=40)
            xml_part, _, act_part = out.partition(_MARK)
            start, end = xml_part.find("<?xml"), xml_part.rfind("</hierarchy>")
            if start != -1 and end != -1:
                m = _ACTIVITY_RE.search(act_part)
                pkg = act = None
                if m:
                    pkg, act = m.group(1), m.group(2)
                    if act.startswith("."):
                        act = pkg + act
                return Snapshot(xml_part[start : end + len("</hierarchy>")], pkg, act)
            last = out[-300:]
            time.sleep(0.6 * (attempt + 1))
        raise DriverError(f"uiautomator dump failed after {retries} tries: {last!r}")

    def screenshot(self, path: str | Path) -> None:
        data = self._run(["exec-out", "screencap", "-p"], binary=True, timeout=30)
        if not data.startswith(b"\x89PNG"):
            raise DriverError("screencap returned no PNG data")
        Path(path).write_bytes(data)

    def keyboard_shown(self) -> bool:
        return "mInputShown=true" in self.shell("dumpsys input_method | grep -m1 mInputShown")

    # ── input ────────────────────────────────────────────────────────────────
    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {x} {y}")

    def long_press(self, x: int, y: int, ms: int = 900) -> None:
        self.shell(f"input swipe {x} {y} {x} {y} {ms}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 450) -> None:
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {ms}")

    def back(self) -> None:
        self.shell("input keyevent KEYCODE_BACK")

    def key(self, code: str) -> None:
        self.shell(f"input keyevent {code}")

    def input_text(self, text: str) -> None:
        # `input text` uses %s for spaces; everything else is shell-quoted for the device shell.
        self.shell(f"input text {shlex.quote(text.replace(' ', '%s'))}")

    def clear_field(self, length: int = 40) -> None:
        self.shell("input keyevent KEYCODE_MOVE_END; input keyevent " + " ".join(["KEYCODE_DEL"] * length))

    def hide_keyboard(self) -> None:
        # ESC closes the IME without the side effects of BACK (which can close a search screen).
        if self.keyboard_shown():
            self.key("KEYCODE_ESCAPE")

    # ── settings ─────────────────────────────────────────────────────────────
    _ANIM_KEYS = ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")

    def get_animations(self) -> dict[str, str]:
        return {k: self.shell(f"settings get global {k}").strip() for k in self._ANIM_KEYS}

    def set_animations(self, values: dict[str, str] | float) -> None:
        for k in self._ANIM_KEYS:
            v = values.get(k, "1.0") if isinstance(values, dict) else values
            if v in (None, "null", ""):
                v = "1.0"
            self.shell(f"settings put global {k} {v}")

    # ── lock task ("screen pinning"): keeps the app in front; BACK at its root and other apps are blocked
    def top_task_id(self, package: str) -> int | None:
        out = self.shell("dumpsys activity activities | grep -m1 topResumedActivity")
        m = re.search(r"u\d+ ([\w.]+)/\S+ t(\d+)\}", out)
        return int(m.group(2)) if m and m.group(1) == package else None

    def pin(self, package: str) -> bool:
        task = self.top_task_id(package)
        if task is None:
            return False
        self.shell(f"am task lock {task}")
        return "PINNED" in self.shell("dumpsys activity activities | grep -m1 mLockTaskModeState")

    def unpin(self) -> None:
        self.shell("am task lock stop")

    def clear_crash_log(self) -> None:
        self.shell("logcat -b crash -c")

    def crash_log(self) -> str:
        return self.shell("logcat -b crash -d -t 300", timeout=30)
