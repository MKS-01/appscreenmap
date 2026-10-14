import json
import time

from appscreenmap.core.analyzer import parse_hierarchy
from appscreenmap.drivers.dumpsys import parse_am_start, parse_framestats, parse_gfx_summary
from appscreenmap.perf import (
    LoadMeter,
    format_perf,
    frame_metrics,
    has_loading_indicator,
    summarize,
)
from appscreenmap.testkit.helpers import hierarchy, node

GFX = """Applications Graphics Acceleration Info:
Uptime: 1234567 Realtime: 1234567

** Graphics info for pid 4321 [dev.mks.duskread] **

Stats since: 1234000000000ns
Total frames rendered: 42
Janky frames: 5 (11.90%)
Janky frames (legacy): 7 (16.67%)
50th percentile: 9ms
90th percentile: 18ms
95th percentile: 25ms
99th percentile: 61ms
Number Missed Vsync: 0
Number High input latency: 2
Number Slow UI thread: 3
Number Slow bitmap uploads: 0
Number Slow issue draw commands: 1
Number Frame deadline missed: 5
"""

FRAMESTATS = """
---PROFILEDATA---
Flags,FrameTimelineVsyncId,IntendedVsync,Vsync,InputEventId,HandleInputStart,AnimationStart,PerformTraversalsStart,DrawStart,FrameDeadline,FrameInterval,FrameStartTime,SyncQueued,SyncStart,IssueDrawCommandsStart,SwapBuffers,FrameCompleted,DequeueBufferDuration,QueueBufferDuration,GpuCompleted,SwapBuffersCompleted,DisplayPresentTime,CommandSubmissionCompleted,
0,1,1000000000,1000000000,0,0,0,0,0,0,16666666,0,0,0,0,0,1008000000,0,0,0,0,0,0,
1,2,1016000000,1016000000,0,0,0,0,0,0,16666666,0,0,0,0,0,1046000000,0,0,0,0,0,0,
0,3,1100000000,1100000000,0,0,0,0,0,0,16666666,0,0,0,0,0,1900000000,0,0,0,0,0,0,
---PROFILEDATA---
"""


def test_parse_gfx_summary_framestats_and_am_start():
    s = parse_gfx_summary(GFX)
    assert s == {
        "frames": 42,
        "janky_frames": 5,
        "janky_pct": 11.9,
        "p50_ms": 9,
        "p90_ms": 18,
        "p95_ms": 25,
        "p99_ms": 61,
        "slow_ui_thread": 3,
        "deadline_missed": 5,
        "high_input_latency": 2,
    }
    frames = parse_framestats(FRAMESTATS)
    assert [f["flags"] for f in frames] == [0, 1, 0]
    m = frame_metrics(frames)
    assert m["render_ms"] == 900 and m["frames"] == 3
    assert m["janky_frames"] == 2 and m["frozen_frames"] == 1 and m["max_frame_ms"] == 800.0
    assert parse_am_start(
        "Status: ok\nLaunchState: COLD\nActivity: x\nTotalTime: 812\nWaitTime: 815\nComplete"
    ) == {"TotalTime": 812, "WaitTime": 815, "LaunchState": "COLD"}
    assert parse_framestats("no data") == [] and frame_metrics([]) == {}
    # With deadlines (Android 12+), jank = finished after the deadline, not "longer than 16 ms".
    late = [
        {"start": 0, "end": 30_000_000, "deadline": 33_000_000, "interval": 16_666_666},
        {"start": 0, "end": 40_000_000, "deadline": 33_000_000, "interval": 16_666_666},
    ]
    assert frame_metrics(late)["janky_frames"] == 1


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


def test_summarize_ranks_screens_and_flags_budget(tmp_path):
    run = tmp_path / "r"
    run.mkdir()
    t = lambda ms, **kw: {"load_ms": ms, "settled": True, "frames": 40, "janky_frames": 1, **kw}
    data = {
        "run": {"id": "r", "config": {"disable_animations": True}},
        "screens": [
            {"id": i, "kind": "app", "title": n}
            for i, n in (("s001", "Home"), ("s002", "Feed"), ("s003", "Settings"))
        ],
        "transitions": [
            {
                "from": "s001",
                "to": "s002",
                "label": "Feed",
                "action": "click",
                "kind": "nav",
                "timings": [t(2900, frozen_frames=1), t(3100, waited_for_loading=True)],
            },
            {
                "from": "s001",
                "to": "s003",
                "label": "Settings",
                "action": "click",
                "kind": "button",
                "timings": [t(300)],
            },
            {
                "from": "s003",
                "to": "s001",
                "label": "Back",
                "action": "back",
                "kind": "back",
                "timings": [t(5000)],
            },
            {
                "from": "s002",
                "to": "s001",
                "label": "Home",
                "action": "click",
                "kind": "nav",
                "inferred": True,
                "timings": [],
            },
        ],
        "events": [],
        "perf": {
            "startup": [{"TotalTime": 820, "LaunchState": "COLD"}, {"TotalTime": 760, "LaunchState": "COLD"}]
        },
    }
    (run / "map.json").write_text(json.dumps(data))
    rep = summarize(run, budget_ms=1000)
    assert [r["screen"] for r in rep["screens"]] == ["s002", "s003"]  # back arrivals don't count as loads
    feed = rep["screens"][0]
    assert feed["median_ms"] == 3000 and feed["rating"] == "slow" and feed["waited_for_loading"]
    assert rep["startup"] == {"samples": 2, "median_ms": 790, "max_ms": 820}
    assert any("s002" in f and "3000 ms" in f for f in rep["findings"])
    assert any("frozen" in f for f in rep["findings"])
    assert (run / "perf.json").is_file()
    assert "🔴" in format_perf(rep) and "Feed" in format_perf(rep)
