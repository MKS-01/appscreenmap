"""Merging runs: unique screen ids, one scenario per run, references rewritten, files copied under the new ids."""

from __future__ import annotations

import json

import pytest

from appscreenmap.core.merge import merge_runs


def make_run(root, name, titles, started):
    d = root / name
    (d / "screens").mkdir(parents=True)
    screens = []
    for i, title in enumerate(titles, 1):
        sid = f"s{i:03d}"
        (d / "screens" / f"{sid}.png").write_bytes(b"png-" + title.encode())
        (d / "screens" / f"{sid}-bottom.png").write_bytes(b"bottom")
        screens.append(
            {
                "id": sid,
                "kind": "app",
                "title": title,
                "activity": "A",
                "depth": i - 1,
                "first_step": i,
                "origin": "launch" if i == 1 else "action",
                "variant_of": None,
                "reach_path": [] if i == 1 else [{"screen": "s001", "key": "k", "label": "go"}],
                "screenshot": f"screens/{sid}.png",
                "thumb": f"screens/{sid}.jpg",
                "hierarchy": f"screens/{sid}.xml",
                "captures": {"bottom": f"screens/{sid}-bottom.png"},
                "elements": [{"id": "e1", "status": "done", "target": "s002" if i == 1 else None}],
            }
        )
    transitions = [
        {"id": "t1", "from": "s001", "to": "s002", "key": "k", "label": "go", "step": 2, "kind": "button"}
    ][: len(titles) - 1]
    m = {
        "schema": 1,
        "run": {
            "id": name,
            "app": {"package": "p", "activities": ["A"]},
            "started_at": started,
            "finished_at": started,
            "steps": 2,
            "elapsed_s": 5,
        },
        "screens": screens,
        "transitions": transitions,
        "events": [{"step": 1, "type": "restart"}],
        "perf": {},
    }
    (d / "map.json").write_text(json.dumps(m))
    return d


def test_merge_gives_unique_ids_and_one_scenario_per_run(tmp_path):
    a = make_run(tmp_path, "pre-20261016-010000", ["Welcome", "Sign up"], "2026-10-16T01:00:00")
    b = make_run(tmp_path, "post-20261016-020000", ["Home", "Explore"], "2026-10-16T02:00:00")
    out = tmp_path / "merged"
    out.mkdir()
    data = merge_runs([a, b], out, "merged-1", ["Pre-auth", "Post-login"])

    assert [s["id"] for s in data["screens"]] == ["s001", "s002", "s003", "s004"]
    assert [s["scenario"] for s in data["screens"]] == ["sc1", "sc1", "sc2", "sc2"]
    assert [sc["entry"] for sc in data["run"]["scenarios"]] == [["s001"], ["s003"]]
    t2 = data["transitions"][1]
    assert (t2["id"], t2["from"], t2["to"], t2["scenario"]) == ("t2", "s003", "s004", "sc2")
    assert t2["step"] > data["transitions"][0]["step"]  # steps keep the scenarios in order
    home = data["screens"][2]
    assert (
        home["screenshot"] == "screens/s003.png" and home["captures"]["bottom"] == "screens/s003-bottom.png"
    )
    assert data["screens"][3]["reach_path"][0]["screen"] == "s003"
    assert data["screens"][2]["elements"][0]["target"] == "s004"
    assert (out / "screens" / "s003.png").read_bytes() == b"png-Home"
    assert (out / "screens" / "s004-bottom.png").exists()
    assert data["stats"]["screens"] == 4 and data["run"]["merged_from"] == [a.name, b.name]


def test_merge_refuses_runs_of_different_apps(tmp_path):
    a = make_run(tmp_path, "a-20261016-010000", ["One"], "2026-10-16T01:00:00")
    b = make_run(tmp_path, "b-20261016-020000", ["Two"], "2026-10-16T02:00:00")
    m = json.loads((b / "map.json").read_text())
    m["run"]["app"]["package"] = "other"
    (b / "map.json").write_text(json.dumps(m))
    out = tmp_path / "merged"
    out.mkdir()
    with pytest.raises(ValueError, match="different apps"):
        merge_runs([a, b], out, "m")


def test_a_canvas_can_be_a_source_and_keeps_its_scenarios(tmp_path):
    a = make_run(tmp_path, "pre-20261016-010000", ["Welcome", "Sign up"], "2026-10-16T01:00:00")
    b = make_run(tmp_path, "post-20261016-020000", ["Home", "Explore"], "2026-10-16T02:00:00")
    c = make_run(tmp_path, "tabs-20261016-030000", ["Hub"], "2026-10-16T03:00:00")
    canvas = tmp_path / "canvas"
    canvas.mkdir()
    merge_runs([a, b], canvas, "canvas", ["Pre-auth", "Post-login"])
    out = tmp_path / "bigger"
    out.mkdir()
    data = merge_runs([canvas, c], out, "canvas", ["", "Tabs"])

    assert [sc["label"] for sc in data["run"]["scenarios"]] == ["Pre-auth", "Post-login", "Tabs"]
    assert [sc["entry"] for sc in data["run"]["scenarios"]] == [["s001"], ["s003"], ["s005"]]
    assert [s["scenario"] for s in data["screens"]] == ["sc1", "sc1", "sc2", "sc2", "sc3"]
    assert data["transitions"][1]["scenario"] == "sc2"


def test_notes_and_titles_follow_their_screens_into_the_canvas(tmp_path):
    a = make_run(tmp_path, "pre-20261016-010000", ["Welcome", "Sign up"], "2026-10-16T01:00:00")
    b = make_run(tmp_path, "post-20261016-020000", ["Home", "Explore"], "2026-10-16T02:00:00")
    (b / "notes.json").write_text(
        json.dumps(
            {
                "appscreenmap_notes": 1,
                "notes": {"s002": {"star": True, "updated": "t"}},
                "a11y": {"s001::touch-target::btn::Go::0,0": {"status": "wontfix", "updated": "t"}},
                "comments": {"c1": {"x": 1, "y": 2, "screen": "s002", "tag": "bug", "text": "Wrong title"}},
                "stickies": {"k1": {"x": 3, "y": 4, "screen": "s002", "text": "Key flow"}},
                "edits": {
                    "titles": {"s001": "Feed"},
                    "deleted": ["s002"],
                    "parents": {"s002": "s001"},
                    "added": {"n-1": {"title": "Filters", "parent": "s001"}},
                    "labels": {"s002": "Explore tab"},
                },
            }
        )
    )
    (b / "titles.json").write_text(json.dumps({"language": "de", "titles": {"s001": "Home (en)"}}))
    out = tmp_path / "merged"
    out.mkdir()
    merge_runs([a, b], out, "merged")  # b's s001, s002 become s003, s004

    doc = json.loads((out / "notes.json").read_text())
    assert doc["run"] == "merged" and doc["notes"] == {"s004": {"star": True, "updated": "t"}}
    assert list(doc["a11y"]) == ["s003::touch-target::btn::Go::0,0"]
    assert doc["comments"]["c1"]["screen"] == "s004"
    assert doc["stickies"]["k1"]["screen"] == "s004"
    assert doc["edits"] == {
        "titles": {"s003": "Feed"},
        "deleted": ["s004"],
        "parents": {"s004": "s003"},
        "added": {"n-1": {"title": "Filters", "parent": "s003", "created": ""}},
        "labels": {"s004": "Explore tab"},
    }
    assert json.loads((out / "titles.json").read_text()) == {
        "language": "de",
        "titles": {"s003": "Home (en)"},
    }


def test_no_notes_file_when_no_source_has_one(tmp_path):
    a = make_run(tmp_path, "pre-20261016-010000", ["Welcome"], "2026-10-16T01:00:00")
    out = tmp_path / "merged"
    out.mkdir()
    merge_runs([a], out, "merged")
    assert not (out / "notes.json").exists() and not (out / "titles.json").exists()


def test_network_logs_and_sessions_follow_their_screens_into_the_canvas(tmp_path):
    a = make_run(tmp_path, "p-a", ["Home", "Settings"], "2026-10-01T00:00:00+00:00")
    b = make_run(tmp_path, "p-b", ["Home", "Network"], "2026-10-02T00:00:00+00:00")
    mb = json.loads((b / "map.json").read_text())
    mb["run"]["network"] = {"mode": "observe", "events": 1}
    (b / "map.json").write_text(json.dumps(mb))
    (b / "network.jsonl").write_text('{"asm": 1, "event": "connect", "host": "api.test", "t": 1}\n')
    (b / "logs.jsonl").write_text('{"asm": 1, "event": "log", "t": 1, "message": "hi"}\n')
    sess = a / "sessions" / "session-1"
    sess.mkdir(parents=True)
    (sess / "session.json").write_text(json.dumps({"id": "session-1", "screens": ["s002"]}))
    (sess / "logs.jsonl").write_text('{"asm": 1, "event": "log", "t": 1, "screen": "s002"}\n')
    (sess / "timeline.jsonl").write_text('{"t": 1, "screen": "s002"}\n')

    out = tmp_path / "canvas"
    out.mkdir()
    m = merge_runs([a, b], out, "canvas")
    net = [json.loads(x) for x in (out / "network.jsonl").read_text().splitlines()]
    assert net == [{"asm": 1, "event": "connect", "host": "api.test", "t": 1, "scenario": "sc2"}]
    assert json.loads((out / "logs.jsonl").read_text())["scenario"] == "sc2"
    assert m["run"]["scenarios"][1]["network"] == {"mode": "observe", "events": 1}
    assert "network" not in m["run"] and "network" not in m["run"]["scenarios"][0]
    # the session was recorded against the first run: its screens keep their (unchanged) ids
    assert json.loads((out / "sessions/session-1/session.json").read_text())["screens"] == ["s002"]

    # merge the canvas again behind a new run: the session's screen ids follow the renumbering
    c = make_run(tmp_path, "p-c", ["Home", "Search", "About"], "2026-09-30T00:00:00+00:00")
    out2 = tmp_path / "canvas2"
    out2.mkdir()
    merge_runs([c, out], out2, "canvas2")
    assert json.loads((out2 / "sessions/session-1/session.json").read_text())["screens"] == ["s005"]
    assert json.loads((out2 / "sessions/session-1/logs.jsonl").read_text())["screen"] == "s005"
    assert json.loads((out2 / "sessions/session-1/timeline.jsonl").read_text())["screen"] == "s005"
    assert [json.loads(x)["scenario"] for x in (out2 / "network.jsonl").read_text().splitlines()] == ["sc3"]


def test_crawl_rows_keep_their_step_and_screen_in_the_canvas(tmp_path):
    a = make_run(tmp_path, "p-a", ["Home", "Settings"], "2026-10-01T00:00:00+00:00")
    b = make_run(tmp_path, "p-b", ["Home", "Network"], "2026-10-02T00:00:00+00:00")
    (b / "network.jsonl").write_text('{"asm": 1, "event": "connect", "t": 5, "screen": "s002", "step": 2}\n')
    (b / "timeline.jsonl").write_text('{"t": 4, "step": 2, "screen": "s002", "title": "Network"}\n')
    (b / "trace.jsonl").write_text(
        '{"step": 2, "t": 3.1, "screen": "s001", "to": "s002", "effect": "new_screen"}\n'
        '{"step": "tap ^Profile$", "t": 3.0, "playbook": "before", "n": 1, "ok": true}\n'
    )
    out = tmp_path / "canvas"
    out.mkdir()
    m = merge_runs([a, b], out, "canvas")
    net = json.loads((out / "network.jsonl").read_text())
    tl = json.loads((out / "timeline.jsonl").read_text())
    network = next(s["id"] for s in m["screens"] if s["title"] == "Network")
    offset = max(t["step"] for t in m["transitions"] if t["scenario"] == "sc1")
    assert net["screen"] == tl["screen"] == network != "s002"
    assert net["step"] == tl["step"] == 2 + offset and net["scenario"] == tl["scenario"] == "sc2"
    # Crawl replay works on the canvas: the step keeps where it led, under the new ids
    tr, play = (json.loads(x) for x in (out / "trace.jsonl").read_text().splitlines())
    assert play["step"] == "tap ^Profile$"  # a playbook row's `step` is its description: kept, not shifted
    assert (tr["to"], tr["step"], tr["scenario"]) == (network, 2 + offset, "sc2") and tr["screen"] != "s001"
