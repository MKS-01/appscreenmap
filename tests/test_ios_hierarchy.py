"""iOS accessibility tree → analyzer input. Uses a real tree recorded from DuskRead on an iPhone 17 simulator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from appscreenmap.analyzer import analyze, parse_hierarchy
from appscreenmap.driver import DriverError
from appscreenmap.driver_ios import IosSimulatorDriver
from appscreenmap.ios_hierarchy import idb_to_xml, is_out_of_process

HOME = json.loads((Path(__file__).parent / "fixtures" / "duskread-ios-home.json").read_text())
BUNDLE = "dev.mks.duskread"


def _tree(**kw):
    return parse_hierarchy(idb_to_xml(HOME, 402, 874, BUNDLE, **kw))


def test_buttons_become_clickable_with_their_accessibility_label():
    root = _tree()
    by_text = {n.text: n for n in root.walk() if n.text}
    for label in ("Settings", "15 MIN", "25 MIN", "30 MIN", "Listen to the week"):
        assert by_text[label].clickable, label
        assert by_text[label].cls == "android.widget.Button"
    # plain text is not tappable
    assert not by_text["Hello, MKS"].clickable
    assert by_text["Hello, MKS"].cls == "android.widget.TextView"


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
    """DuskRead's floating bottom bar: four icon buttons drawn on screen, none in the tree (found on a simulator,
    Oct 2026). The crawler cannot tap what VoiceOver cannot see; the analyzer reports the screen as having no nav."""
    in_bar = [n for n in HOME if n["type"] == "Button" and 795 <= n["frame"]["y"] <= 850]
    assert in_bar == []  # only card text lies under the bar; no tab buttons are exposed
    labels = {n.get("AXLabel") for n in HOME}
    assert not labels & {"Home", "Following", "Saved", "Player"}


# ── the driver, with a fake command runner ──────────────────────────────────


class Fake:
    def __init__(self, tree):
        self.calls: list[list[str]] = []
        self.tree = tree

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
        if "launchctl" in joined:
            return "123\t0\tUIKitApplication:dev.mks.duskread[abcd][rb-legacy]\n"
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
        d.install("DuskRead.ipa")

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
