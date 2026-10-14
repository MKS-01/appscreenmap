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
    assert "🔴" in format_perf(rep) and "Feed" in format_perf(rep)
