"""iOS Simulator driver: the same surface the explorer uses on Android, over `xcrun simctl` + `idb`.

  simctl  boots, installs, launches, terminates, screenshots, grants permissions.
  idb     reads the accessibility tree and sends taps, swipes and text (simctl cannot do either).

Coordinates are iOS points (what idb reports and accepts); screenshots are native pixels, so the viewer scales by
the width/height ratio exactly as it does for Android screens at different densities.

Not here yet: crash detection (needs a log predicate), `clear_data` for an app without reinstalling, and physical
devices (idb_companion supports them; the plumbing differs). See docs/PLAN.md, phase 3.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import ClassVar
from urllib.parse import unquote, urlparse

from .driver import DriverError, Snapshot
from .ios_hierarchy import element_type, idb_to_xml, is_out_of_process

_STATE = re.compile(r"\((Booted|Shutdown|Shutting Down|Creating)\)")


class IosSimulatorDriver:
    platform = "ios"

    def __init__(self, udid: str | None = None, run=None):
        self._run_fn = run or self._exec
        self.udid = udid or self._pick_device()
        self._idb = self._find_idb()
        self._info: dict | None = None
        self._size: tuple[int, int] | None = None
        self._crash_mark = time.time()
        self._executable: dict[str, str] = {}

    # ── process plumbing ────────────────────────────────────────────────────

    @staticmethod
    def _exec(args: list[str], timeout: float = 60, binary: bool = False, check: bool = True):
        p = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        if check and p.returncode != 0:
            raise DriverError(
                f"{' '.join(args[:4])} failed: {p.stderr.decode(errors='replace').strip()[-300:]}"
            )
        return p.stdout if binary else p.stdout.decode(errors="replace")

    def _simctl(self, *args: str, timeout: float = 60, check: bool = True, binary: bool = False):
        return self._run_fn(["xcrun", "simctl", *args], timeout=timeout, check=check, binary=binary)

    @staticmethod
    def _find_idb() -> list[str]:
        if shutil.which("idb"):
            return ["idb"]
        if shutil.which("uvx"):
            return ["uvx", "--from", "fb-idb", "idb"]
        raise DriverError(
            "idb not found. Install it: `brew install facebook/fb/idb-companion` and `uv tool install fb-idb`"
        )

    def _idb_run(self, *args: str, timeout: float = 40, check: bool = True) -> str:
        return self._run_fn([*self._idb, *args, "--udid", self.udid], timeout=timeout, check=check)

    # ── devices ─────────────────────────────────────────────────────────────

    @classmethod
    def list_devices(cls, run=None) -> list[tuple[str, str]]:
        """(udid, "iPhone 17 · iOS 27.0") for every booted simulator."""
        out = (run or cls._exec)(
            ["xcrun", "simctl", "list", "devices", "booted", "--json"], timeout=30, check=False
        )
        try:
            data = json.loads(out).get("devices", {})
        except (json.JSONDecodeError, AttributeError):
            return []
        found = []
        for runtime, devices in data.items():
            os_name = runtime.rsplit(".", 1)[-1].replace("-", " ", 1).replace("-", ".")
            for d in devices:
                if d.get("state") == "Booted":
                    found.append((d["udid"], f"{d['name']} · {os_name}"))
        return found

    def _pick_device(self) -> str:
        devices = self.list_devices(self._run_fn)
        if not devices:
            raise DriverError(
                "no booted iOS simulator. Boot one: `xcrun simctl boot <name>` and open Device Hub"
            )
        if len(devices) > 1:
            raise DriverError(
                "several booted simulators; pass --serial <udid>: " + ", ".join(u for u, _ in devices)
            )
        return devices[0][0]

    def info(self) -> dict:
        """Device record in the shape map.json expects (see docs/MAP_SCHEMA.md "device"). Sizes are points, and
        `density` is 160 so px-per-dp is 1: the accessibility checks then read points as dp, as intended."""
        if self._info is None:
            meta = {}
            try:
                for runtime, devices in (
                    json.loads(self._simctl("list", "devices", "--json", check=False))
                    .get("devices", {})
                    .items()
                ):
                    for d in devices:
                        if d["udid"] == self.udid:
                            meta = {
                                "name": d["name"],
                                "release": runtime.rsplit(".", 1)[-1].removeprefix("iOS-").replace("-", "."),
                            }
            except (json.JSONDecodeError, AttributeError):
                pass
            w, h = self.screen_size()
            name = meta.get("name", "iOS Simulator")
            self._info = {
                "serial": self.udid,
                "platform": "ios",
                "type": "emulator",
                "name": f"{name} (Simulator)",
                "model": name,
                "manufacturer": "Apple",
                "form_factor": "tablet" if "iPad" in name else "phone",
                "os": {"name": "iOS", "release": meta.get("release", "")},
                "width": w,
                "height": h,
                "density": 160,
                "font_scale": self.get_font_scale(),
                "display": {
                    "width_dp": w,
                    "height_dp": h,
                    "window_class": "compact" if w < 600 else "medium" if w < 840 else "expanded",
                },
            }
        return self._info

    def screen_size(self) -> tuple[int, int]:
        """Screen size in points, from the application node idb reports."""
        if self._size is None:
            nodes = self._describe()
            app = next((n for n in nodes if element_type(n) == "Application"), None)
            if not app:
                raise DriverError(
                    "the accessibility tree has no application node; is an app in the foreground?"
                )
            f = app["frame"]
            self._size = (round(f["width"]), round(f["height"]))
        return self._size

    # ── app lifecycle ───────────────────────────────────────────────────────

    def install(self, app: str | Path, grant: bool = True) -> None:
        """Install a simulator build (a `.app` folder). An `.ipa` is device-signed and cannot run in the simulator."""
        p = Path(app)
        if p.suffix == ".ipa":
            raise DriverError(
                "an .ipa is built for devices; the simulator needs the .app from an iphonesimulator build"
            )
        self._simctl("install", self.udid, str(p), timeout=120)

    def is_installed(self, bundle_id: str) -> bool:
        return self._simctl("get_app_container", self.udid, bundle_id, check=False).strip() != ""

    def app_version(self, bundle_id: str) -> str | None:
        out = self._simctl("appinfo", self.udid, bundle_id, check=False)
        m = re.search(r"CFBundleShortVersionString\s*=\s*\"?([^\";\n]+)", out)
        return m.group(1).strip() if m else None

    def launch(self, bundle_id: str, activity: str | None = None) -> dict:
        self._remember_executable(bundle_id)
        out = self._simctl("launch", self.udid, bundle_id, timeout=60)
        return {"pid": out.strip().rsplit(" ", 1)[-1]}

    def force_stop(self, bundle_id: str) -> None:
        self._simctl("terminate", self.udid, bundle_id, check=False)

    def grant_all(self, bundle_id: str) -> None:
        self._simctl("privacy", self.udid, "grant", "all", bundle_id, check=False)

    # ── observing ───────────────────────────────────────────────────────────

    def _describe(self, retries: int = 3) -> list[dict]:
        last = ""
        for attempt in range(retries):
            out = self._idb_run("ui", "describe-all", check=False)
            try:
                nodes = json.loads(out)
                if isinstance(nodes, list) and nodes:
                    return nodes
            except json.JSONDecodeError:
                last = out[-200:]
            time.sleep(0.6 * (attempt + 1))
        raise DriverError(f"idb describe-all returned no tree after {retries} tries: {last!r}")

    def snapshot(self, retries: int = 3) -> Snapshot:
        """The accessibility tree as hierarchy XML. `activity` is None: iOS has no activity, so screens are told apart
        by structure and text alone (the analyzer's signature already works that way for single-activity apps).

        The package is the bundle id of the process that owns the tree. A tree with no content (an in-app browser,
        a system sheet) is reported as `ios.external`, so the explorer treats it as having left the app."""
        nodes = self._describe(retries)
        w, h = self.screen_size()
        app = next((n for n in nodes if element_type(n) == "Application"), {})
        out = is_out_of_process(nodes)
        bundle = (
            "ios.external" if out else (self._bundle_of(app.get("pid")) or app.get("AXLabel") or "unknown")
        )
        snap = Snapshot(idb_to_xml(nodes, w, h, bundle), bundle, None)
        snap.out_of_process = out  # type: ignore[attr-defined]
        return snap

    def _bundle_of(self, pid) -> str | None:
        """Bundle id of the running app with this pid (`launchctl list` names every UIKit app the simulator runs)."""
        if pid is None:
            return None
        out = self._simctl("spawn", self.udid, "launchctl", "list", check=False)
        for line in out.splitlines():
            m = re.match(r"\s*(\d+)\s+\S+\s+UIKitApplication:([\w.\-]+)\[", line)
            if m and int(m.group(1)) == int(pid):
                return m.group(2)
        return None

    def screenshot(self, path: str | Path) -> None:
        self._simctl("io", self.udid, "screenshot", str(path), timeout=30)
        if not Path(path).exists():
            raise DriverError("simctl screenshot wrote no file")

    def keyboard_shown(self) -> bool:
        return any(element_type(n) == "Keyboard" for n in self._describe())

    # ── acting ──────────────────────────────────────────────────────────────

    def tap(self, x: int, y: int) -> None:
        self._idb_run("ui", "tap", str(x), str(y))

    def long_press(self, x: int, y: int, ms: int = 900) -> None:
        self._idb_run("ui", "tap", str(x), str(y), "--duration", f"{ms / 1000:.2f}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 450) -> None:
        self._idb_run("ui", "swipe", str(x1), str(y1), str(x2), str(y2), "--duration", f"{ms / 1000:.2f}")

    def back(self) -> None:
        """iOS has no Back key. Inside an app the convention is the edge swipe; this is only used to leave a screen the
        crawler itself opened (never to leave the app: the lock rules in explorer.py still apply)."""
        w, h = self.screen_size()
        self.swipe(2, h // 2, w - 40, h // 2, 250)

    def input_text(self, text: str) -> None:
        self._idb_run("ui", "text", text)

    def hide_keyboard(self) -> None:
        # A tap on the status-bar area dismisses most keyboards without activating anything.
        w, _ = self.screen_size()
        self.tap(w // 2, 60)

    def clear_field(self, length: int = 40) -> None:
        for _ in range(length):
            self._idb_run("ui", "key", "42", check=False)  # HID usage 0x2A: delete

    # ── the app lock, animations, text size ─────────────────────────────────

    def pin(self, bundle_id: str) -> bool:
        """Android pins the task; iOS has no scriptable equivalent (Guided Access needs a passcode UI). The lock is
        enforced by the explorer instead: any screen whose package isn't the app's counts as having left it, and the
        crawl restarts the app rather than pressing Back into another app."""
        return True

    def unpin(self) -> None:
        return None

    def get_animations(self) -> dict[str, str]:
        return {}

    def set_animations(self, values) -> None:
        return (
            None  # no system-wide switch on iOS; SwiftUI honours Reduce Motion, which is a separate setting
        )

    _SIZES: ClassVar[list[tuple[str, float]]] = [
        ("extra-small", 0.82), ("small", 0.88), ("medium", 0.94), ("large", 1.0), ("extra-large", 1.12),
        ("extra-extra-large", 1.23), ("extra-extra-extra-large", 1.35), ("accessibility-medium", 1.64),
        ("accessibility-large", 1.95), ("accessibility-extra-large", 2.35),
        ("accessibility-extra-extra-large", 2.76), ("accessibility-extra-extra-extra-large", 3.12),
    ]  # fmt: skip

    def get_font_scale(self) -> float:
        """Dynamic Type size as a scale (1.0 = the default, "large")."""
        current = self._simctl("ui", self.udid, "content_size", check=False).strip()
        return next((scale for name, scale in self._SIZES if name == current), 1.0)

    def set_font_scale(self, scale: float) -> None:
        """Set Dynamic Type to the size nearest this scale. 2.0 lands on accessibility-large (1.95): WCAG 1.4.4 at 200%."""
        name = min(self._SIZES, key=lambda s: abs(s[1] - scale))[0]
        self._simctl("ui", self.udid, "content_size", name)
        self._info = None

    # ── crashes ─────────────────────────────────────────────────────────────

    def clear_crash_log(self) -> None:
        self._crash_mark = time.time()

    def crash_log(self) -> str:
        """Newest crash report for the app launched last, written since `clear_crash_log`. The simulator's crashes land
        in ~/Library/Logs/DiagnosticReports. The first line is `Process: <bundle>, …` so the explorer's check (written for
        Android's logcat) recognises it."""
        reports = Path.home() / "Library" / "Logs" / "DiagnosticReports"
        found = []
        for bundle, exe in self._executable.items():
            for f in reports.glob(f"{exe}*.ips"):
                if f.stat().st_mtime >= self._crash_mark:
                    found.append((f.stat().st_mtime, bundle, f))
        if not found:
            return ""
        _, bundle, f = max(found)
        return f"Process: {bundle}, report {f.name}\n" + f.read_text(errors="replace")

    def _remember_executable(self, bundle_id: str) -> None:
        if bundle_id not in self._executable:
            m = re.search(
                r"CFBundleExecutable\s*=\s*\"?([^\";\n]+)",
                self._simctl("appinfo", self.udid, bundle_id, check=False),
            )
            if m:
                self._executable[bundle_id] = m.group(1).strip()

    # ── data ────────────────────────────────────────────────────────────────

    def clear_data(self, bundle_id: str) -> None:
        """Empty the app's data container (documents, caches, preferences) without reinstalling it. The keychain is
        shared by the whole simulator and is left alone."""
        self.force_stop(bundle_id)
        out = self._simctl("get_app_container", self.udid, bundle_id, "data", check=False).strip()
        if not out:
            raise DriverError(f"{bundle_id} is not installed on {self.udid}")
        root = Path(unquote(urlparse(out).path) if out.startswith("file:") else out)
        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                child.mkdir(exist_ok=True)  # the system expects Documents/, Library/, tmp/ to exist
            else:
                child.unlink(missing_ok=True)
