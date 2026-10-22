from __future__ import annotations

import json

from appscreenmap.reports.perf import format_perf, summarize


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
    assert "SLOW" in format_perf(rep) and "Feed" in format_perf(rep)


def test_network_per_screen_names_the_slowest_request_and_its_phase(tmp_path):
    run = tmp_path / "r"
    run.mkdir()
    data = {
        "run": {"id": "r", "config": {}},
        "screens": [
            {"id": "s001", "kind": "app", "title": "Home"},
            {"id": "s002", "kind": "app", "title": "Network check"},
        ],
        "transitions": [],
        "events": [],
    }
    (run / "map.json").write_text(json.dumps(data))
    rows = [
        {"event": "connect", "host": "api.playground.test", "t": 10.0, "screen": "s002"},
        {"event": "connect_failed", "host": "events.tracker.test", "t": 10.1, "screen": "s002"},
        {
            "event": "request",
            "scheme": "http",
            "method": "GET",
            "host": "cdn.playground.test",
            "path": "/banner.png",
            "t": 10.2,
            "t_end": 11.6,
            "timing": {"send": 1, "wait": 1300, "receive": 90},
            "screen": "s002",
        },
        {
            "event": "request",
            "scheme": "https",
            "method": "GET",
            "host": "x.test",
            "path": "/a",
            "t": 3,
            "t_end": 3.1,
        },
        "not ours",
    ]
    (run / "network.jsonl").write_text(
        "".join((json.dumps({"asm": 1, **r}) if isinstance(r, dict) else r) + "\n" for r in rows)
    )
    rep = summarize(run, budget_ms=1000)
    (s,) = rep["network"]["screens"]  # Home made no calls, so it has no row; the unattributed one is counted
    assert rep["network"]["measured"] == "proxy" and rep["network"]["unattributed"] == 1
    assert (s["screen"], s["requests"], s["tunnels"], s["failed"], s["cleartext"]) == ("s002", 1, 1, 1, 1)
    assert s["hosts"] == ["api.playground.test", "cdn.playground.test", "events.tracker.test"]
    assert s["slowest"] == {
        "method": "GET",
        "host": "cdn.playground.test",
        "path": "/banner.png",
        "ms": 1400,
        "phase": "wait",
    }
    assert any(
        "waits 1400 ms on GET cdn.playground.test/banner.png (proxy-measured, mostly wait)" in f
        for f in rep["findings"]
    )
    assert "network per screen (measured at the proxy" in format_perf(rep)
    assert json.loads((run / "perf.json").read_text())["network"]["screens"][0]["screen"] == "s002"


def test_no_network_key_without_a_capture(tmp_path):
    run = tmp_path / "r"
    run.mkdir()
    (run / "map.json").write_text(
        json.dumps({"run": {"id": "r"}, "screens": [], "transitions": [], "events": []})
    )
    assert summarize(run)["network"] is None
