"""Screens filed by hand: ids continue, nothing existing changes, links and scenarios follow, bad input writes nothing."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from appscreenmap.core import manual

XML = (
    '<?xml version="1.0"?><hierarchy rotation="0"><node class="android.widget.FrameLayout" package="p" '
    'bounds="[0,0][100,200]"><node class="android.widget.TextView" package="p" text="Support" '
    'bounds="[0,0][100,50]"/></node></hierarchy>'
)


def png(fmt="PNG", size=(100, 200)):
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, fmt)
    return out.getvalue()


def canvas(tmp_path):
    d = tmp_path / "canvas"
    (d / "screens").mkdir(parents=True)
    row = {
        "id": "s001",
        "kind": "app",
        "title": "Home",
        "depth": 0,
        "scenario": "sc1",
        "reach_path": [],
        "elements": [],
    }
    data = {
        "schema": 1,
        "run": {"id": "canvas", "app": {"package": "p"}, "scenarios": [{"id": "sc1", "screens": ["s001"]}]},
        "screens": [row, {"id": "x:other", "kind": "external", "scenario": "sc1"}],
        "transitions": [{"id": "t1", "from": "s001", "to": "s001", "label": "x"}],
        "events": [],
        "stats": {"screens": 1, "transitions": 1},
    }
    (d / "map.json").write_text(json.dumps(data))
    return d


def read(d):
    return json.loads((d / "map.json").read_text())


def test_adds_a_screen_under_a_parent_without_touching_the_rest(tmp_path):
    d = canvas(tmp_path)
    before = read(d)
    row = manual.add_screen(d, png(), "Support", parent="s001", via="Help", hierarchy=XML)
    data = read(d)
    assert row["id"] == "s002" and row["source"] == "manual" and row["scenario"] == "sc1"
    assert row["reach_path"] == [] and row["depth"] == 1 and "S:TextView|" in row["tokens"]
    assert data["screens"][0] == before["screens"][0] and data["screens"][1] == before["screens"][1]
    t = data["transitions"][-1]
    assert (t["id"], t["from"], t["to"], t["label"], t["source"]) == ("t2", "s001", "s002", "Help", "manual")
    assert data["run"]["scenarios"][0]["screens"] == ["s001", "s002"]
    assert data["stats"]["screens"] == 2 and data["stats"]["transitions"] == 2
    edits = json.loads((d / "notes.json").read_text())[
        "edits"
    ]  # the viewer's tree reads its parent from here
    assert edits["parents"] == {"s002": "s001"} and edits["labels"] == {"s002": "Help"}
    for f in ("screens/s002.png", "screens/s002.jpg", "screens/s002.xml"):
        assert (d / f).is_file()


def test_a_jpeg_is_stored_as_png_and_ids_keep_counting(tmp_path):
    d = canvas(tmp_path)
    manual.add_screen(d, png("JPEG"), "One")
    row = manual.add_screen(d, png(), "Two")
    assert row["id"] == "s003" and (d / "screens/s002.png").read_bytes()[:4] == b"\x89PNG"
    assert read(d)["transitions"][-1]["id"] == "t1"  # no parent, no link


@pytest.mark.parametrize(
    "kw",
    [
        {"image": b"not an image"},
        {"image": png("GIF")},
        {"title": "  "},
        {"parent": "s099"},
        {"parent": "x:other"},
        {"via": "Help"},  # a link label without a parent
        {"scenario": "sc9"},
        {"hierarchy": "<<<"},
    ],
)
def test_bad_input_raises_and_writes_nothing(tmp_path, kw):
    d = canvas(tmp_path)
    before = (d / "map.json").read_text()
    args = {"image": png(), "title": "Support", **kw}
    with pytest.raises(manual.ManualError):
        manual.add_screen(d, args.pop("image"), args.pop("title"), **args)
    assert (d / "map.json").read_text() == before and not list((d / "screens").iterdir())


def test_editing_keeps_map_titles_and_notes_in_step(tmp_path):
    d = canvas(tmp_path)
    manual.add_screen(d, png(), "Support", parent="s001", via="Help")
    manual.add_screen(d, png(), "Other")
    (d / "titles.json").write_text(json.dumps({"language": "zh", "titles": {"s002": "old"}}))
    (d / "notes.json").write_text(
        json.dumps({"appscreenmap_notes": 1, "notes": {}, "edits": {"titles": {"s002": "stale"}}})
    )
    manual.update_screen(d, "s002", title="Help centre", parent="s003", via="Open help")
    data = read(d)
    assert next(s for s in data["screens"] if s["id"] == "s002")["title"] == "Help centre"
    links = [t for t in data["transitions"] if t["to"] == "s002"]
    assert [(t["from"], t["label"]) for t in links] == [("s003", "Open help")]
    assert json.loads((d / "titles.json").read_text())["titles"]["s002"] == "Help centre"
    assert json.loads((d / "notes.json").read_text())["edits"]["titles"]["s002"] == "Help centre"
    assert data["stats"]["transitions"] == len(data["transitions"])
    assert json.loads((d / "notes.json").read_text())["edits"]["parents"]["s002"] == "s003"


def test_a_crawled_screen_is_never_edited(tmp_path):
    d = canvas(tmp_path)
    with pytest.raises(manual.ManualError, match="crawled"):
        manual.update_screen(d, "s001", title="Nope")


def test_replacing_a_manual_screens_image_updates_size_and_thumb(tmp_path):
    d = canvas(tmp_path)
    manual.add_screen(d, png(size=(100, 200)), "Page")
    row = manual.update_screen(d, "s002", image=png(size=(300, 600)))
    assert (row["width"], row["height"]) == (300, 600) and read(d)["screens"][-1]["width"] == 300
    with Image.open(d / "screens/s002.png") as im, Image.open(d / "screens/s002.jpg") as th:
        assert im.size == (300, 600) and th.size[0] == 360
    with pytest.raises(manual.ManualError):
        manual.update_screen(d, "s002", image=b"nope")


def test_an_id_the_notes_still_mention_is_not_reused(tmp_path):
    d = canvas(tmp_path)
    (d / "notes.json").write_text(
        json.dumps({"appscreenmap_notes": 1, "notes": {}, "edits": {"deleted": ["s002", "s003"]}})
    )
    row = manual.add_screen(d, png(), "Fresh", parent="s001")
    assert row["id"] == "s004"
    edits = json.loads((d / "notes.json").read_text())["edits"]
    assert edits["deleted"] == ["s002", "s003"] and edits["parents"] == {"s004": "s001"}


def test_a_new_scenario_starts_a_tree_of_its_own(tmp_path):
    d = canvas(tmp_path)
    root = manual.add_screen(d, png(), "Step 1", new_scenario="Onboarding")
    child = manual.add_screen(d, png(), "Step 2", parent=root["id"], via="Continue")
    again = manual.add_screen(d, png(), "Other root", new_scenario="Onboarding")  # same label: same scenario
    data = read(d)
    sc = next(c for c in data["run"]["scenarios"] if c.get("label") == "Onboarding")
    assert sc["id"] == "sc2" and root["scenario"] == child["scenario"] == again["scenario"] == "sc2"
    assert sc["screens"] == [root["id"], child["id"], again["id"]] and sc["entry"] == [
        root["id"],
        again["id"],
    ]
    edits = json.loads((d / "notes.json").read_text())["edits"]
    assert edits["parents"] == {root["id"]: None, child["id"]: root["id"], again["id"]: None}
    with pytest.raises(manual.ManualError):
        manual.add_screen(d, png(), "Bad", parent="s001", new_scenario="X")


def test_manual_screens_sort_after_everything_already_on_the_canvas(tmp_path):
    d = canvas(tmp_path)
    data = read(d)
    data["screens"][0]["first_step"] = 40
    (d / "map.json").write_text(json.dumps(data))
    a = manual.add_screen(d, png(), "A", new_scenario="Onboarding")
    b = manual.add_screen(d, png(), "B", parent=a["id"])
    assert (a["first_step"], b["first_step"]) == (41, 42)


def test_a_manual_screen_takes_a_new_hierarchy_and_a_bottom_capture(tmp_path):
    d = canvas(tmp_path)
    manual.add_screen(d, png(), "Tab")
    row = manual.update_screen(d, "s002", hierarchy=XML, captures={"bottom": png(size=(100, 300))})
    assert row["hierarchy"] == "screens/s002.xml" and "S:TextView|" in row["tokens"]
    assert (
        row["captures"] == {"bottom": "screens/s002-bottom.png"} and (d / "screens/s002-bottom.png").is_file()
    )
    assert read(d)["screens"][-1]["captures"]["bottom"] == "screens/s002-bottom.png"
    with pytest.raises(manual.ManualError):
        manual.update_screen(d, "s002", captures={"Bad Name": png()})
