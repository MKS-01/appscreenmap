"""Text-aware visual diff: strings and bounds from the hierarchy, no OCR."""

import json

from PIL import Image

from appscreenmap.regression.visual import changed_regions, diff_runs, text_changed, text_diff, text_nodes
from appscreenmap.testkit.helpers import PKG, hierarchy, node


def tv(bounds, text, rid=""):
    return node("android.widget.TextView", bounds, text=text, rid=rid)


def nodes(*children, height=2400):
    return text_nodes(hierarchy(*children), height, PKG, mask_top=0.045)


def diff(a, b, size_a=(1080, 2400), size_b=(1080, 2400)):
    return text_diff(a, b, size_a, size_b)


def test_identical_screens_have_no_text_changes():
    a = nodes(tv((40, 200, 600, 260), "Settings"), tv((40, 300, 600, 360), "Dark mode"))
    r = diff(a, a)
    assert r["changes"] == [] and not text_changed(r)


def test_added_removed_moved_and_changed():
    base = nodes(
        tv((40, 200, 600, 260), "Settings"),
        tv((40, 300, 600, 360), "Dark mode"),
        tv((40, 400, 600, 460), "Sign out", rid=f"{PKG}:id/signout"),
        tv((40, 500, 600, 560), "Help"),
    )
    cand = nodes(
        tv((40, 200, 600, 260), "Settings"),  # same
        tv((40, 700, 600, 760), "Dark mode"),  # moved down
        tv((40, 400, 600, 460), "Log out", rid=f"{PKG}:id/signout"),  # same id, new text
        tv((40, 900, 600, 960), "Privacy"),  # added
    )  # "Help" removed
    r = diff(base, cand)
    kinds = {(c["type"], c["text"]) for c in r["changes"]}
    assert kinds == {
        ("moved", "Dark mode"),
        ("changed", "Log out"),
        ("added", "Privacy"),
        ("removed", "Help"),
    }
    changed = next(c for c in r["changes"] if c["type"] == "changed")
    assert changed["base_text"] == "Sign out" and changed["digits_only"] is False
    moved = next(c for c in r["changes"] if c["type"] == "moved")
    assert moved["base_bounds"] == [40, 300, 600, 360] and moved["cand_bounds"] == [40, 700, 600, 760]
    assert (r["added"], r["removed"], r["moved"], r["changed"]) == (1, 1, 1, 1)


def test_text_in_the_same_place_without_an_id_counts_as_changed():
    r = diff(nodes(tv((40, 300, 600, 360), "Save")), nodes(tv((40, 302, 600, 362), "Save changes")))
    assert [(c["type"], c["base_text"], c["text"]) for c in r["changes"]] == [
        ("changed", "Save", "Save changes")
    ]


def test_digit_only_changes_are_data_not_ui():
    r = diff(nodes(tv((40, 300, 600, 360), "14:59")), nodes(tv((40, 300, 600, 360), "14:58")))
    assert r["changed"] == 1 and r["changes"][0]["digits_only"] is True
    assert not text_changed(r)


def test_positions_compare_relative_to_screen_size():
    base = nodes(tv((40, 300, 600, 360), "Title"))
    # Same layout on a 1440x3200 screen: everything scaled by 4/3.
    cand = text_nodes(hierarchy(tv((53, 400, 800, 480), "Title")), 3200, PKG)
    assert diff(base, cand, (1080, 2400), (1440, 3200))["changes"] == []


def test_status_bar_and_other_windows_are_ignored():
    xml = hierarchy(
        tv((0, 0, 200, 60), "12:01"),  # inside the masked status bar band
        node(
            "android.widget.TextView",
            (40, 300, 600, 360),
            text="Keyboard key",
            package="com.google.android.inputmethod.latin",
        ),
        tv((40, 400, 600, 460), "App text"),
    )
    assert [n["text"] for n in text_nodes(xml, 2400, PKG, mask_top=0.045)] == ["App text"]


def test_changed_regions_report_direction():
    a = Image.new("RGB", (200, 400), "white")
    b = a.copy()
    b.paste((0, 0, 0), (20, 40, 80, 100))  # darker block
    a.paste((0, 0, 0), (120, 300, 180, 360))  # was dark, now white: brighter
    mask = Image.new("L", a.size, 0)
    mask.paste(255, (20, 40, 80, 100))
    mask.paste(255, (120, 300, 180, 360))
    regions = changed_regions(mask, a, b)
    assert len(regions) == 2
    by_dir = {r["direction"]: r["bounds"] for r in regions}
    assert set(by_dir) == {"darker", "brighter"}
    x1, y1, x2, y2 = by_dir["darker"]
    assert x1 <= 20 and y1 <= 40 and x2 >= 80 and y2 >= 100


def _run(root, rid, xml):
    d = root / rid
    (d / "screens").mkdir(parents=True)
    Image.new("RGB", (1080, 2400), "white").save(d / "screens" / "s001.png")
    (d / "screens" / "s001.xml").write_text(xml)
    screen = {
        "id": "s001",
        "kind": "app",
        "title": "Settings",
        "signature": "sig",
        "tokens": ["S:x"],
        "activity": "Main",
        "package": PKG,
        "width": 1080,
        "height": 2400,
        "screenshot": "screens/s001.png",
        "hierarchy": "screens/s001.xml",
    }
    run = {"id": rid, "app": {"package": PKG}}
    (d / "map.json").write_text(json.dumps({"schema": 1, "run": run, "screens": [screen], "transitions": []}))
    return d


def test_diff_runs_flags_a_text_change_the_pixels_missed(tmp_path):
    base = _run(tmp_path, "base", hierarchy(tv((40, 300, 600, 360), "Sign out")))
    cand = _run(tmp_path, "cand", hierarchy(tv((40, 300, 600, 360), "Log out")))
    rep = diff_runs(base, cand)
    item = rep["items"][0]
    assert item["changed_ratio"] == 0  # identical screenshots
    assert item["status"] == "changed" and item["text"]["changed"] == 1
    assert (cand / item["diff"]).is_file()
