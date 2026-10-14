"""A fake device running a tiny app described by hierarchies and a navigation table. No emulator needed."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from appscreenmap.driver import Snapshot
from appscreenmap.testkit.helpers import PKG, hierarchy, node

ACT = f"{PKG}.MainActivity"


def btn(bounds, text="", desc=""):
    return node("android.widget.Button", bounds, clickable=True, focusable=True, text=text, desc=desc)


def title(text):
    return node("android.widget.TextView", (40, 150, 600, 220), text=text, rid=f"{PKG}:id/title")


SCREENS = {
    "home": hierarchy(
        title("Home"),
        btn((100, 300, 500, 420), text="Settings"),
        btn((100, 500, 500, 620), text="About"),
    ),
    "settings": hierarchy(
        title("Settings"),
        btn((900, 150, 1040, 260), desc="Close settings"),
        node(
            "android.widget.Switch",
            (100, 400, 1000, 500),
            clickable=True,
            checkable=True,
            focusable=True,
            text="Dark mode",
        ),
    ),
    "about": hierarchy(
        title("About"),
        node("android.widget.TextView", (40, 300, 1000, 360), text="Version 1.0"),
    ),
}
# (screen, tap target text/desc) → next screen
NAV = {("home", "Settings"): "settings", ("home", "About"): "about", ("settings", "Close settings"): "home"}

_LABEL_BOUNDS = re.compile(r'(?:text|content-desc)="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')


class FakeApp:
    def __init__(self, screens=None, nav=None, start="home", version="1.0"):
        self.screens = screens or SCREENS
        self.nav = nav or NAV
        self.start, self.version = start, version
        self.screen, self.stack, self.frames, self.taps, self.typed = start, [], 0, [], []

    def tap(self, x, y):
        for m in _LABEL_BOUNDS.finditer(self.screens[self.screen]):
            label, x1, y1, x2, y2 = m.group(1), *map(int, m.groups()[1:])
            if x1 <= x <= x2 and y1 <= y <= y2 and (self.screen, label) in self.nav:
                self.stack.append(self.screen)
                self.screen = self.nav[(self.screen, label)]
                self.frames += 12
                self.taps.append(label)
                return
        self.frames += 2  # pressed state redraw

    def back(self):
        if self.stack:  # pinned: BACK on the root does nothing
            self.screen = self.stack.pop()
            self.frames += 10


class FakeDriver:
    serial = "fake"

    def __init__(self, app: FakeApp | None = None):
        self.app = app or FakeApp()
        self.pinned = False
        self.cleared = 0

    def screen_size(self):
        return 1080, 2400

    def info(self):
        return {"serial": "fake", "model": "Fake", "width": 1080, "height": 2400, "density": 420}

    def app_version(self, pkg):
        return self.app.version

    def snapshot(self, retries=3):
        return Snapshot(self.app.screens[self.app.screen], PKG, ACT)

    def screenshot(self, path):
        Image.new("RGB", (1080, 2400), "white").save(path)

    def tap(self, x, y):
        self.app.tap(x, y)

    def long_press(self, x, y, ms=900):
        pass

    def swipe(self, *a, **k):
        pass

    def back(self):
        self.app.back()

    def key(self, code):
        pass

    def input_text(self, text):
        self.app.typed.append(text)

    def hide_keyboard(self):
        pass

    def keyboard_shown(self):
        return False

    def force_stop(self, pkg):
        self.app.screen, self.app.stack = self.app.start, []

    def clear_data(self, pkg):
        self.cleared += 1

    def grant_all(self, pkg):
        pass

    def launch(self, pkg, activity):
        self.app.frames += 20
        return {"LaunchState": "COLD", "TotalTime": 640, "WaitTime": 650}

    def pin(self, pkg):
        self.pinned = True
        return True

    def unpin(self):
        self.pinned = False

    def get_animations(self):
        return {}

    def set_animations(self, values):
        pass

    def get_font_scale(self):
        return 1.0

    def set_font_scale(self, scale):
        pass

    def crash_log(self):
        return ""

    def clear_crash_log(self):
        pass

    def gfx_reset(self, pkg):
        self.app.frames = 0

    def frames_rendered(self, pkg):
        return self.app.frames

    def gfx_summary(self, pkg):
        return {"frames": self.app.frames}

    def gfx_framestats(self, pkg):
        return []


def crawl(tmp: Path, driver: FakeDriver, run_id: str = "proj-1", **cfg_overrides):
    """Crawl the fake app into tmp/proj/<run_id>; returns (run_dir, explorer)."""
    from appscreenmap.core.config import CrawlConfig
    from appscreenmap.core.model import AppMap
    from appscreenmap.explorer import Explorer

    cfg = CrawlConfig(
        **{
            "max_steps": 60,
            "settle_seconds": 0,
            "launch_wait_seconds": 0,
            "load_quiet_ms": 40,
            "load_timeout_s": 2,
            **cfg_overrides,
        }
    )
    run_dir = tmp / "proj" / run_id
    run_dir.mkdir(parents=True)
    amap = AppMap(
        {
            "id": run_id,
            "status": "running",
            "started_at": "2026-10-13T00:00:00+00:00",
            "app": {"package": PKG, "launch_activity": ACT, "version": driver.app.version, "label": "Fake"},
            "device": {"width": 1080, "height": 2400, "density": 420},
            "config": cfg.to_dict(),
        }
    )
    ex = Explorer(driver, PKG, ACT, cfg, run_dir, amap, log=lambda *a: None)
    ex.run()
    amap.run["status"] = "done"
    ex.save()
    return run_dir, ex
