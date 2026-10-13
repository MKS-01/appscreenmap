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
        if self._info is None:
            out = self._simctl("list", "devices", "--json", check=False)
            meta = {}
            try:
                for runtime, devices in json.loads(out).get("devices", {}).items():
                    for d in devices:
                        if d["udid"] == self.udid:
                            meta = {"model": d["name"], "runtime": runtime.rsplit(".", 1)[-1]}
            except (json.JSONDecodeError, AttributeError):
                pass
            w, h = self.screen_size()
            self._info = {
                "serial": self.udid,
                "platform": "ios",
                "manufacturer": "Apple",
                "width": w,
                "height": h,
                **meta,
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
        by structure and text alone (the analyzer's signature already works that way for single-activity apps)."""
        nodes = self._describe(retries)
        w, h = self.screen_size()
        app = next((n for n in nodes if element_type(n) == "Application"), {})
        bundle = self._frontmost_bundle() or app.get("AXLabel") or "unknown"
        xml = idb_to_xml(nodes, w, h, bundle)
        snap = Snapshot(xml, bundle, None)
        snap.out_of_process = is_out_of_process(nodes)  # type: ignore[attr-defined]
        return snap

    def _frontmost_bundle(self) -> str | None:
        out = self._simctl("spawn", self.udid, "launchctl", "list", check=False)
        for line in out.splitlines():
            m = re.search(r"UIKitApplication:([\w.\-]+)\[", line)
            if m:
                return m.group(1)
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

    def clear_data(self, bundle_id: str) -> None:
        raise DriverError(
            "clear_data needs the app reinstalled on iOS; pass the .app via --app so it can be reinstalled"
        )
