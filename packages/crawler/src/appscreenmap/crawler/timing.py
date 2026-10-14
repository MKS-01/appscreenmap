"""Navigation performance: how long a screen takes to load after an action, and how smoothly it renders.

How it is measured (no app instrumentation needed):
- Before an action, the app's frame stats are reset (`dumpsys gfxinfo <pkg> reset`).
- After the action, the app's rendered-frame counter is polled until it stops changing for
  `quiet_ms`. The app has finished drawing: the screen is *visually settled*.
- If the settled screen still shows a loading indicator, we wait for the next burst of frames
  (the content arriving) and settle again.
- The load time is the host-measured time from the action to the last frame change. Frame stats
  (`framestats`) give the precise on-device render span and jank for the same window.
- App start uses `am start -W` (TotalTime) on every cold relaunch.

The resolution is one poll (~50–100 ms over adb). Numbers are for comparing screens and builds on
the same device, not absolute truths. Animations follow the crawl setting (`disable_animations`):
off gives content-only times, on gives what a user sees.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from appscreenmap.drivers.dumpsys import frame_metrics

_LOADING_RE = re.compile(r"\b(loading|please wait|fetching|syncing)\b", re.IGNORECASE)


@dataclass
class Timing:
    load_ms: int | None  # action → screen visually settled (host clock)
    settled: bool  # False: the app never stopped drawing within the timeout
    render_ms: int | None = None  # first → last frame of the window (device clock, from framestats)
    frames: int = 0
    janky_frames: int = 0
    frozen_frames: int = 0
    p90_frame_ms: float | None = None
    max_frame_ms: float | None = None
    waited_for_loading: bool = False
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            k: v
            for k, v in self.__dict__.items()
            if v not in (None, {}, False) or k in ("settled", "load_ms")
        }
        return d


def has_loading_indicator(root) -> bool:
    """A visible progress indicator or 'Loading…' text on the screen."""
    for n in root.walk():
        if n.area <= 0:
            continue
        if "ProgressBar" in n.cls or "CircularProgress" in n.cls or "LinearProgress" in n.cls:
            return True
        if _LOADING_RE.search(n.text or "") or _LOADING_RE.search(n.desc or ""):
            return True
    return False


class LoadMeter:
    def __init__(
        self, driver, package: str, quiet_ms: int = 400, timeout_s: float = 10.0, min_wait_s: float = 0.15
    ):
        self.d = driver
        self.pkg = package
        self.quiet = quiet_ms / 1000
        self.timeout = timeout_s
        self.min_wait = min_wait_s
        self.t0: float | None = None

    def begin(self) -> None:
        """Call right before the action."""
        self.d.gfx_reset(self.pkg)
        self.t0 = time.monotonic()

    def wait_settled(self, until_new_frames: bool = False) -> tuple[bool, float]:
        """Poll the frame counter until it stops changing. Returns (settled, seconds from t0 to last change)."""
        assert self.t0 is not None, "begin() first"
        time.sleep(self.min_wait)
        last = self.d.frames_rendered(self.pkg)
        last_change = time.monotonic() if (last or 0) > 0 else self.t0
        start_count = last
        while True:
            now = time.monotonic()
            if now - self.t0 > self.timeout:
                return False, last_change - self.t0
            count = self.d.frames_rendered(self.pkg)
            now = time.monotonic()
            if count != last:
                last, last_change = count, now
                continue
            waiting_for_burst = until_new_frames and count == start_count
            if not waiting_for_burst and now - last_change >= self.quiet:
                return True, last_change - self.t0

    def finish(self, settled: bool, seconds: float, waited_for_loading: bool = False) -> Timing:
        t = Timing(load_ms=round(seconds * 1000), settled=settled, waited_for_loading=waited_for_loading)
        try:
            t.stats = self.d.gfx_summary(self.pkg)
            fm = frame_metrics(self.d.gfx_framestats(self.pkg))
        except Exception:  # noqa: BLE001 — metrics are best effort; never break a crawl
            fm = {}
        for k, v in fm.items():
            setattr(t, k, v)
        # Prefer the platform's own counts for the same window when gfxinfo reports them.
        if "janky_frames" in t.stats and "frames" in t.stats:
            t.frames, t.janky_frames = t.stats["frames"], t.stats["janky_frames"]
        return t
