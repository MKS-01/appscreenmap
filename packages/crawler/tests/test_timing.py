from __future__ import annotations

import time

from appscreenmap.core.analyzer import parse_hierarchy
from appscreenmap.crawler.timing import LoadMeter, has_loading_indicator
from appscreenmap.testkit.helpers import hierarchy, node


class FakeDevice:
    """Frame counter that keeps rising for `busy_s` after the action, then stops."""

    def __init__(self, busy_s: float, burst_after_s: float | None = None):
        self.busy_s, self.burst_after = busy_s, burst_after_s
        self.t0 = None

    def gfx_reset(self, pkg):
        self.t0 = time.monotonic()

    def frames_rendered(self, pkg):
        dt = time.monotonic() - self.t0
        frames = int(min(dt, self.busy_s) * 60)
        if self.burst_after is not None and dt > self.burst_after:
            frames += int(min(dt - self.burst_after, 0.1) * 60) + 1
        return frames

    def gfx_summary(self, pkg):
        return {"frames": 10}

    def gfx_framestats(self, pkg):
        return []


def test_load_meter_waits_until_frames_stop():
    meter = LoadMeter(FakeDevice(busy_s=0.3), "pkg", quiet_ms=150, timeout_s=3, min_wait_s=0.02)
    meter.begin()
    settled, secs = meter.wait_settled()
    assert settled and 0.25 <= secs <= 0.45
    t = meter.finish(settled, secs)
    assert t.settled and t.stats == {"frames": 10} and 250 <= t.load_ms <= 450


def test_load_meter_times_out_on_endless_animation_and_waits_for_content_burst():
    meter = LoadMeter(FakeDevice(busy_s=99), "pkg", quiet_ms=150, timeout_s=0.4, min_wait_s=0.02)
    meter.begin()
    settled, _ = meter.wait_settled()
    assert not settled
    # Static spinner: nothing drawn until the content arrives at 0.35 s.
    meter = LoadMeter(
        FakeDevice(busy_s=0.05, burst_after_s=0.35), "pkg", quiet_ms=100, timeout_s=3, min_wait_s=0.02
    )
    meter.begin()
    settled, secs = meter.wait_settled()  # the screen with the spinner settles first…
    assert settled and secs < 0.2
    settled, secs = meter.wait_settled(until_new_frames=True)  # …then the content arrives
    assert settled and secs >= 0.35


def test_loading_indicator_detection():
    spinner = parse_hierarchy(hierarchy(node("android.widget.ProgressBar", (500, 1100, 580, 1180))))
    text = parse_hierarchy(
        hierarchy(node("android.widget.TextView", (0, 0, 400, 80), text="Loading articles…"))
    )
    done = parse_hierarchy(hierarchy(node("android.widget.TextView", (0, 0, 400, 80), text="Downloads")))
    assert has_loading_indicator(spinner) and has_loading_indicator(text) and not has_loading_indicator(done)
