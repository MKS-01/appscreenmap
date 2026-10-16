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
