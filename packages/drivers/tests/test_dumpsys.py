from __future__ import annotations

from appscreenmap.drivers.dumpsys import frame_metrics, parse_am_start, parse_framestats, parse_gfx_summary

GFX = """Applications Graphics Acceleration Info:
Uptime: 1234567 Realtime: 1234567

** Graphics info for pid 4321 [dev.mks.sample-app] **

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
