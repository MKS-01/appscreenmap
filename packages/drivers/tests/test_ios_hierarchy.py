"""iOS accessibility tree → analyzer input. Uses a real tree recorded from a reading app on an iPhone 17 simulator (names neutralised)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from appscreenmap.core.analyzer import analyze, parse_hierarchy
from appscreenmap.drivers.base import DriverError
from appscreenmap.drivers.ios import IosSimulatorDriver
from appscreenmap.drivers.ios_hierarchy import (
    collapsed_tab_bar,
    idb_to_xml,
    is_out_of_process,
    tab_from_point,
)

HOME = json.loads((Path(__file__).parent / "fixtures" / "ios-reader-home.json").read_text())
BUNDLE = "com.example.reader"


def _tree(**kw):
    return parse_hierarchy(idb_to_xml(HOME, 402, 874, BUNDLE, **kw))


def test_buttons_become_clickable_with_their_accessibility_label():
    root = _tree()
    by_text = {n.text: n for n in root.walk() if n.text}
    for label in ("Settings", "15 MIN", "25 MIN", "30 MIN", "Listen to the week"):
        assert by_text[label].clickable, label
        assert by_text[label].cls == "android.widget.Button"
    # plain text is not tappable
    assert not by_text["Good evening"].clickable
    assert by_text["Good evening"].cls == "android.widget.TextView"


def test_bounds_are_points_clipped_to_the_screen_and_offscreen_nodes_dropped():
    offscreen = {
        "type": "StaticText",
        "AXLabel": "below the fold",
        "frame": {"x": 14, "y": 1000, "width": 100, "height": 20},
    }
    straddling = {
        "type": "Button",
        "AXLabel": "half",
        "frame": {"x": 300, "y": 860, "width": 200, "height": 60},
    }
    root = parse_hierarchy(idb_to_xml([*HOME[:3], offscreen, straddling], 402, 874, BUNDLE))
    texts = [n.text for n in root.walk()]
    assert "below the fold" not in texts
    half = next(n for n in root.walk() if n.text == "half")
    assert half.bounds == (300, 860, 402, 874)  # clipped to the 402x874 screen
    settings = next(n for n in root.walk() if n.text == "Settings")
    assert settings.bounds == (354, 73, 388, 107)


def test_the_screen_is_analysed_like_an_android_one():
    obs = analyze(idb_to_xml(HOME, 402, 874, BUNDLE), BUNDLE, None, 402, 874)
    labels = {e.label for e in obs.elements}
    assert {"Settings", "15 MIN", "25 MIN", "30 MIN"} <= labels
    assert all(e.bounds[2] <= 402 and e.bounds[3] <= 874 for e in obs.elements)
    assert obs.signature  # identity works with no activity


def test_identifier_becomes_a_resource_id_and_text_fields_use_the_label_as_hint():
    tree = [
        {"type": "Application", "AXLabel": "App", "frame": {"x": 0, "y": 0, "width": 402, "height": 874}},
        {
            "type": "TextField",
            "AXLabel": "Email",
            "AXValue": "me@x.dev",
            "AXUniqueId": "email",
            "frame": {"x": 20, "y": 100, "width": 360, "height": 44},
        },
        {
            "type": "SecureTextField",
            "AXLabel": "Password",
            "frame": {"x": 20, "y": 160, "width": 360, "height": 44},
        },
        {
            "type": "Switch",
            "AXLabel": "Weekly digest",
            "AXValue": "1",
            "frame": {"x": 20, "y": 220, "width": 51, "height": 31},
        },
    ]
    root = parse_hierarchy(idb_to_xml(tree, 402, 874, "dev.x"))
    email, password, switch = [n for n in root.walk() if n.cls.endswith(("EditText", "Switch"))]
    assert email.rid == "dev.x:id/email" and email.text == "me@x.dev" and email.hint == "Email"
    assert password.password and password.hint == "Password"
    assert switch.checkable and switch.checked


def test_an_in_app_browser_has_a_tree_of_one_node():
    only_app = [HOME[0]]
    assert is_out_of_process(only_app)
    assert not is_out_of_process(HOME)


def test_a_control_with_no_accessibility_element_is_simply_absent():
    """The app's floating bottom bar: four icon buttons drawn on screen, none in the tree (found on a simulator,
    Oct 2026). The crawler cannot tap what VoiceOver cannot see; the analyzer reports the screen as having no nav."""
    in_bar = [n for n in HOME if n["type"] == "Button" and 795 <= n["frame"]["y"] <= 850]
    assert in_bar == []  # only card text lies under the bar; no tab buttons are exposed
    labels = {n.get("AXLabel") for n in HOME}
    assert not labels & {"Home", "Following", "Saved", "Player"}


# ── the driver, with a fake command runner ──────────────────────────────────


class Fake:
    def __init__(self, tree, points=None):
        self.calls: list[list[str]] = []
        self.tree = tree
        self.points = points  # (x, y) -> the node `describe-point` returns there

    def __call__(self, args, timeout=60, binary=False, check=True):
        self.calls.append(args)
        joined = " ".join(args)
        if "list devices booted --json" in joined:
            return json.dumps(
                {
                    "devices": {
                        "com.apple.CoreSimulator.SimRuntime.iOS-27-0": [
                            {"udid": "U1", "name": "iPhone 17", "state": "Booted"}
                        ]
                    }
                }
            )
        if "describe-all" in joined:
            return json.dumps(self.tree)
        if "describe-point" in joined and self.points:
            i = args.index("describe-point")
            return json.dumps(self.points(int(args[i + 1]), int(args[i + 2])))
        if "launchctl" in joined:
            return (
                "9001\t0\tUIKitApplication:com.apple.mobilecal[dad3][rb-legacy]\n"
                f"{HOME[0]['pid']}\t0\tUIKitApplication:com.example.reader[abcd][rb-legacy]\n"
            )
        return ""


def test_driver_picks_the_one_booted_simulator_and_reads_points():
    d = IosSimulatorDriver(run=Fake(HOME))
    assert d.udid == "U1"
    assert d.screen_size() == (402, 874)
    snap = d.snapshot()
    assert snap.package == BUNDLE and snap.activity is None
    assert 'bounds="[354,73][388,107]"' in snap.xml


def test_driver_sends_taps_through_idb_in_points():
    fake = Fake(HOME)
    d = IosSimulatorDriver(run=fake)
    d.tap(371, 90)
    d.swipe(200, 600, 200, 200, 450)
    taps = [c for c in fake.calls if "tap" in c]
    assert taps and taps[-1][-5:-1] == ["ui", "tap", "371", "90"] or "371" in taps[-1]
    assert any("swipe" in c and "600" in c for c in fake.calls)


def test_driver_refuses_an_ipa_and_several_simulators():
    d = IosSimulatorDriver(run=Fake(HOME))
    with pytest.raises(DriverError, match="ipa"):
        d.install("Reader.ipa")

    class Two(Fake):
        def __call__(self, args, **kw):
            if "list devices booted --json" in " ".join(args):
                dev = lambda u: {"udid": u, "name": "iPhone", "state": "Booted"}
                return json.dumps(
                    {"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-27-0": [dev("A"), dev("B")]}}
                )
            return super().__call__(args, **kw)

    with pytest.raises(DriverError, match="several"):
        IosSimulatorDriver(run=Two(HOME))


# ── what the crawl relies on ────────────────────────────────────────────────


def test_a_tree_with_no_content_is_reported_as_another_package(monkeypatch):
    """An in-app browser or system sheet: the explorer must see a package that isn't the app's, so it restarts the app
    (never presses Back into it)."""
    d = IosSimulatorDriver(run=Fake([HOME[0]]))
    snap = d.snapshot()
    assert snap.package == "ios.external" and snap.out_of_process


def test_the_bundle_is_the_process_that_owns_the_tree_not_the_first_app_running():
    d = IosSimulatorDriver(run=Fake(HOME))
    assert d.snapshot().package == BUNDLE  # com.apple.mobilecal is listed first by launchctl


def test_font_scale_maps_to_dynamic_type_and_back():
    calls = []

    class Ui(Fake):
        current = "large"

        def __call__(self, args, **kw):
            if (
                args[:3] == ["xcrun", "simctl", "ui"] and len(args) > 5
            ):  # xcrun simctl ui <udid> content_size <name>
                Ui.current = args[5]
                calls.append(args[5])
                return ""
            if args[:3] == ["xcrun", "simctl", "ui"]:
                return Ui.current + "\n"
            return super().__call__(args, **kw)

    d = IosSimulatorDriver(run=Ui(HOME))
    assert d.get_font_scale() == 1.0
    d.set_font_scale(2.0)  # WCAG 1.4.4: 200%
    assert calls[-1] == "accessibility-large" and d.get_font_scale() == 1.95
    d.set_font_scale(1.0)
    assert calls[-1] == "large"


def test_clear_data_empties_the_container_but_keeps_its_folders(tmp_path):
    for sub in ("Documents", "Library", "tmp"):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / "state.db").write_text("x")
    (tmp_path / "stray.txt").write_text("x")

    class Container(Fake):
        def __call__(self, args, **kw):
            if "get_app_container" in args:
                return f"{tmp_path}\n"
            return super().__call__(args, **kw)

    IosSimulatorDriver(run=Container(HOME)).clear_data(BUNDLE)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Documents", "Library", "tmp"]
    assert not any(list(p.iterdir()) for p in tmp_path.iterdir())


def test_crash_log_finds_a_new_report_for_the_launched_app(tmp_path, monkeypatch):
    reports = tmp_path / "Library" / "Logs" / "DiagnosticReports"
    reports.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    class Info(Fake):
        def __call__(self, args, **kw):
            if "appinfo" in args:
                return '{ CFBundleExecutable = Reader; CFBundleIdentifier = "com.example.reader"; }'
            return super().__call__(args, **kw)

    d = IosSimulatorDriver(run=Info(HOME))
    d.launch(BUNDLE)
    (reports / "Reader-2026-10-13-120000.ips").write_text("old crash")
    old = reports / "Reader-2026-10-13-120000.ips"
    import os
    import time

    os.utime(old, (time.time() - 3600, time.time() - 3600))
    d.clear_crash_log()
    assert d.crash_log() == ""  # the old report predates the mark
    (reports / "Reader-2026-10-13-130000.ips").write_text('{"exception": "EXC_BAD_ACCESS"}')
    log = d.crash_log()
    assert (
        log.startswith(f"Process: {BUNDLE},") and "EXC_BAD_ACCESS" in log
    )  # the format the explorer looks for


# ── a tab bar idb lists as one group (found with the iOS Playground, Oct 2026) ──────────────────────────────

_TABS = [
    ("Home", "house", 25),
    ("Search", "magnifyingglass", 91),
    ("Library", "heart", 194),
    ("Profile", "person", 279),
]


def _tab_point(x, y, selected="Home"):
    for label, ident, left in _TABS:
        if left <= x < left + 98 and 795 <= y < 849:
            return {
                "type": "RadioButton",
                "subrole": "AXTabButton",
                "traits": ["TabButton", "Button"],
                "AXLabel": label,
                "AXUniqueId": ident,
                "AXValue": 1 if label == selected else 0,
                "frame": {"x": left, "y": 795, "width": 98, "height": 54},
                "pid": 7,
            }
    return {"type": "Group", "AXLabel": "Tab Bar", "frame": {"x": 0, "y": 791, "width": 402, "height": 83}}


_BAR_TREE = [
    {
        "type": "Application",
        "AXLabel": "Playground",
        "pid": 7,
        "frame": {"x": 0, "y": 0, "width": 402, "height": 874},
    },
    {"type": "Heading", "AXLabel": "Discover", "frame": {"x": 16, "y": 120, "width": 139, "height": 41}},
    {
        "type": "Group",
        "AXLabel": "Tab Bar",
        "traits": ["Scrollable"],
        "frame": {"x": 0, "y": 791, "width": 402, "height": 83},
    },
]


def test_a_collapsed_tab_bar_is_found_and_a_complete_one_is_left_alone():
    assert collapsed_tab_bar(_BAR_TREE) == (0, 791, 402, 83)
    with_tabs = _BAR_TREE + [tab_from_point(_tab_point(30, 820))]
    assert collapsed_tab_bar(with_tabs) is None
    assert collapsed_tab_bar(HOME) is None  # no tab bar at all


def test_the_driver_recovers_the_tabs_idb_leaves_out_and_they_become_tappable_buttons():
    fake = Fake(_BAR_TREE, points=_tab_point)
    d = IosSimulatorDriver(run=fake)
    root = parse_hierarchy(d.snapshot().xml)
    tabs = [n for n in root.walk() if n.text in {"Home", "Search", "Library", "Profile"}]
    assert [n.text for n in tabs] == ["Home", "Search", "Library", "Profile"]
    assert all(n.clickable and n.cls == "android.widget.Button" for n in tabs)
    assert [n.selected for n in tabs] == [True, False, False, False]
    assert sum("describe-point" in c for c in fake.calls) <= 8  # bounded: about one probe per tab


def test_a_tree_without_a_tab_bar_costs_no_extra_calls():
    fake = Fake(HOME, points=_tab_point)
    IosSimulatorDriver(run=fake).snapshot()
    assert not any("describe-point" in c for c in fake.calls)
