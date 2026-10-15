"""The SVG export: well-formed, self-contained, one card per screen, an arrow per transition."""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

import pytest

from appscreenmap.exporters.svg import LAYOUTS, map_svg, write_map_svg

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
NS = {"s": "http://www.w3.org/2000/svg"}


def _screen(i, title, depth, **kw):
    return {
        "id": f"s{i:03d}",
        "kind": "app",
        "title": title,
        "depth": depth,
        "first_step": i,
        "width": 1080,
        "height": 2400,
        "screenshot": f"screens/s{i:03d}.png",
        "thumb": f"screens/s{i:03d}.jpg",
        **kw,
    }


def _tr(i, a, b, label, step, **kw):
    return {"id": f"t{i}", "from": a, "to": b, "action": "click", "label": label, "step": step, **kw}


@pytest.fixture
def run(tmp_path):
    (tmp_path / "screens").mkdir()
    for i in (1, 2, 3):
        (tmp_path / "screens" / f"s{i:03d}.png").write_bytes(PNG)
        (tmp_path / "screens" / f"s{i:03d}.jpg").write_bytes(PNG)
    data = {
        "run": {"id": "r1", "app": {"label": "Demo & Co", "package": "x"}},
        "screens": [
            _screen(1, "Sign <in>", 0),
            _screen(2, "Home", 1),
            _screen(3, "Settings", 1),
            _screen(4, "Browser", 2, kind="other", screenshot=None, thumb=None),
            _screen(5, "No picture", 2, screenshot="screens/missing.png", thumb="screens/missing.jpg"),
        ],
        "transitions": [
            _tr(1, "s001", "s002", "Sign in", 2),
            _tr(2, "s001", "s003", "Settings", 3),
            _tr(3, "s002", "s004", "Link", 4),
            _tr(4, "s002", "s005", "Open", 5),
            _tr(5, "s003", "s002", "Home", 6),  # a link that is not a tree edge
            _tr(6, "s002", "s002", "self", 7),  # self loop: ignored
            _tr(7, "s002", "s005", "Open again", 8),  # same pair: one arrow, labels joined
        ],
    }
    return data, tmp_path


def _boxes(root):
    out = {}
    for g in root.iterfind(".//s:g[@id='screens']/s:g", NS):
        r = g.find("s:rect", NS)
        out[g.get("id")] = tuple(float(r.get(k)) for k in ("x", "y", "width", "height"))
    return out


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_is_well_formed_with_a_card_per_screen(run, layout):
    data, d = run
    root = ET.fromstring(map_svg(data, d, layout))
    assert len(_boxes(root)) == 5
    assert root.get("viewBox") == f"0 0 {root.get('width')} {root.get('height')}"


@pytest.mark.parametrize("layout", LAYOUTS)
def test_cards_do_not_overlap_and_stay_on_the_canvas(run, layout):
    data, d = run
    root = ET.fromstring(map_svg(data, d, layout))
    boxes = list(_boxes(root).values())
    w, h = float(root.get("width")), float(root.get("height"))
    for i, (x, y, bw, bh) in enumerate(boxes):
        assert x >= 0 and y >= 0 and x + bw <= w and y + bh <= h
        for x2, y2, bw2, bh2 in boxes[i + 1 :]:
            assert x + bw <= x2 or x2 + bw2 <= x or y + bh <= y2 or y2 + bh2 <= y


def test_screenshots_are_embedded_and_nothing_loads_from_outside(run):
    data, d = run
    svg = map_svg(data, d, "graph")
    assert svg.count("<image ") == 3  # the other-app card and the missing file get placeholders
    assert "data:image/png;base64," in svg
    assert "http://" not in svg.replace("http://www.w3.org/", "") and "https://" not in svg
    assert "no screenshot" in svg and "left the app" in svg


def test_titles_are_escaped_and_layers_are_named_by_screen_id(run):
    data, d = run
    svg = map_svg(data, d, "tree")
    assert "Sign &lt;in&gt;" in svg and "Demo &amp; Co" in svg
    ids = {g.get("id") for g in ET.fromstring(svg).iterfind(".//s:g[@id='screens']/s:g", NS)}
    assert "s001-Sign-in" in ids and "s002-Home" in ids


def test_graph_draws_every_pair_once_and_tree_only_the_tree_edges(run):
    data, d = run
    graph = ET.fromstring(map_svg(data, d, "graph"))
    tree = ET.fromstring(map_svg(data, d, "tree"))
    count = lambda root: len(root.findall(".//s:g[@id='transitions']/s:path[@fill='none']", NS))
    assert count(graph) == 5  # 6 real pairs minus none: s2->s5 merges, the self loop is dropped
    assert count(tree) == 4  # the s3->s2 link is not how s2 was first reached
    assert "Open · Open again" in map_svg(data, d, "graph")
    assert ET.fromstring(map_svg(data, d, "storyboard")).find(".//s:g[@id='transitions']", NS) is None


def test_thumbs_option_embeds_the_small_image(run):
    data, d = run
    (d / "screens" / "s001.png").write_bytes(PNG + b"FULL")
    assert len(map_svg(data, d, "tree", full_res=True)) > len(map_svg(data, d, "tree", full_res=False))


def test_dark_theme_and_bad_inputs(run):
    data, d = run
    assert "#0a0a0a" in map_svg(data, d, "tree", theme="dark")
    with pytest.raises(ValueError, match="layout"):
        map_svg(data, d, "radial")
    with pytest.raises(ValueError, match="no screens"):
        map_svg({"run": {}, "screens": [], "transitions": []}, d)


def test_unreachable_screens_still_get_a_place(run):
    data, d = run
    data["transitions"] = []
    for layout in LAYOUTS:
        assert len(_boxes(ET.fromstring(map_svg(data, d, layout)))) == 5


def test_write_map_svg_defaults_to_the_run_folder(run):
    import json

    data, d = run
    (d / "map.json").write_text(json.dumps({"schema": 1, **data}))
    path = write_map_svg(d, "graph", full_res=False)
    assert path == d / "map-graph.svg" and path.read_text().startswith("<svg")


def test_graph_wraps_a_crowded_depth_so_the_drawing_is_not_a_tall_strip(tmp_path):
    screens = [_screen(1, "Root", 0)] + [_screen(i, f"Item {i}", 1) for i in range(2, 14)]
    data = {
        "run": {"id": "r"},
        "screens": screens,
        "transitions": [_tr(i, "s001", f"s{i:03d}", "open", i) for i in range(2, 14)],
    }
    root = ET.fromstring(map_svg(data, tmp_path, "graph"))
    w, h = float(root.get("width")), float(root.get("height"))
    assert h < w * 1.5  # it was one 12-screen column, about five times taller than wide
