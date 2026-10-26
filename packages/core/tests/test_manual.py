"""Screens filed by hand: ids continue, nothing existing changes, links and scenarios follow, bad input writes nothing."""

from __future__ import annotations

import hashlib
import io
import json
import threading

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


def test_bad_input_raises_and_writes_nothing(tmp_path):
    d = canvas(tmp_path)
    before = (d / "map.json").read_text()
    for kw in (
        {"image": b"not an image"},
        {"title": "  "},
        {"parent": "s099"},
        {"via": "Help"},  # a link label without a parent
        {"scenario": "sc9"},
        {"hierarchy": "<<<"},
        {"image": png()[:-40]},  # cut off: the header is fine, the pixels are not
    ):
        args = {"image": png(), "title": "Support", **kw}
        with pytest.raises(manual.ManualError):
            manual.add_screen(d, args.pop("image"), args.pop("title"), **args)
        assert (d / "map.json").read_text() == before and not list((d / "screens").iterdir()), kw


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


def snapshot(d):
    """Every file under the canvas, by content, to prove a refused edit changed nothing."""
    return {
        str(p.relative_to(d)): hashlib.md5(p.read_bytes()).hexdigest()
        for p in sorted(d.rglob("*"))
        if p.is_file()
    }


def test_a_refused_edit_changes_nothing(tmp_path):
    d = canvas(tmp_path)
    manual.add_screen(d, png(), "Tab", parent="s001")
    before = snapshot(d)
    small = png(size=(30, 30))
    for kw in (
        {"image": small, "parent": "s099"},
        {"image": small, "scenario": "nope"},
        {"image": small, "captures": {"BAD name": png()}},
        {"hierarchy": XML, "parent": "s099"},
    ):
        with pytest.raises(manual.ManualError):
            manual.update_screen(d, "s002", **kw)
        assert snapshot(d) == before, list(kw)


def test_a_screen_cannot_go_under_itself_or_its_children(tmp_path):
    d = canvas(tmp_path)
    a = manual.add_screen(d, png(), "A", parent="s001")["id"]
    b = manual.add_screen(d, png(), "B", parent=a)["id"]
    c = manual.add_screen(d, png(), "C", parent=b)["id"]
    before = snapshot(d)
    for bad in (a, b, c):  # itself, a child, a grandchild
        with pytest.raises(manual.ManualError, match="itself or one of its own children"):
            manual.update_screen(d, a, parent=bad)
    assert snapshot(d) == before
    manual.update_screen(d, c, parent="s001")  # a move that makes no loop is fine
    with pytest.raises(manual.ManualError, match="app screen"):
        manual.update_screen(d, c, parent="x:other")


def test_non_text_fields_are_a_clean_error(tmp_path):
    d = canvas(tmp_path)
    manual.add_screen(d, png(), "Tab")
    for kw in ({"scenario": ["a"]}, {"via": 5, "parent": "s001"}, {"title": 7}):
        with pytest.raises(manual.ManualError):
            manual.update_screen(d, "s002", **kw)
        with pytest.raises(manual.ManualError):
            manual.add_screen(d, png(), kw.get("title", "X"), **{k: v for k, v in kw.items() if k != "title"})


def test_a_decompression_bomb_is_refused_not_a_crash(tmp_path):
    d = canvas(tmp_path)
    out = io.BytesIO()
    Image.new("1", (20000, 20000)).save(out, "PNG")  # a few KB on disk, 400 MP decoded
    with pytest.raises(manual.ManualError):
        manual.add_screen(d, out.getvalue(), "Bomb")
    assert not list((d / "screens").iterdir()) and len(read(d)["screens"]) == 2


def test_control_characters_are_dropped_from_titles_and_labels(tmp_path):
    d = canvas(tmp_path)
    row = manual.add_screen(d, png(), "a\x00b\x1b[31m\nX", parent="s001", via="go\x07 now")
    assert row["title"] == "a b [31m X" and read(d)["transitions"][-1]["label"] == "go now"


def test_writers_in_parallel_do_not_collide(tmp_path):
    d = canvas(tmp_path)
    ids, errors = [], []

    def add(i):
        try:
            ids.append(manual.add_screen(d, png(), f"Shot {i}", parent="s001")["id"])
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=add, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(set(ids)) == 8
    assert len([s for s in read(d)["screens"] if s.get("source") == "manual"]) == 8
