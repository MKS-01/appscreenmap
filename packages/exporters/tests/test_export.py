from __future__ import annotations

from appscreenmap.exporters.maestro import maestro_flow
from appscreenmap.exporters.mermaid import mermaid
from appscreenmap.testkit.helpers import PKG


def _map_dict():
    return {
        "run": {"id": "r1", "app": {"package": PKG}, "device": {"width": 1080, "height": 2400}},
        "screens": [
            {
                "id": "s001",
                "kind": "app",
                "title": "Sign in",
                "reach_path": [],
                "elements": [],
                "autofill": [{"selector": {"point": [540, 460]}, "value": "qa@x.dev"}],
            },
            {
                "id": "s002",
                "kind": "app",
                "title": "Home",
                "autofill": [],
                "elements": [{"text": "Home", "rid": "", "kind": "button"}],
                "reach_path": [
                    {
                        "screen": "s001",
                        "action": "click",
                        "label": "Sign in",
                        "selector": {"id": f"{PKG}:id/submit", "text": "Sign in", "point": [540, 900]},
                        "scroll_depth": 0,
                    }
                ],
            },
            {
                "id": "s003",
                "kind": "app",
                "title": "Item (1)",
                "autofill": [],
                "elements": [],
                "reach_path": [
                    {
                        "screen": "s002",
                        "action": "click",
                        "label": "Item (1)",
                        "selector": {"text": "Item (1)", "point": [540, 1900]},
                        "scroll_depth": 2,
                    }
                ],
            },
            {"id": "x:com.android.chrome", "kind": "external", "title": "com.android.chrome"},
        ],
        "transitions": [
            {"from": "s001", "to": "s002", "label": "Sign in", "action": "click"},
            {"from": "s002", "to": "x:com.android.chrome", "label": 'Open "site"', "action": "click"},
        ],
    }


def test_maestro_flow_replays_autofill_and_path():
    d = _map_dict()
    flow = maestro_flow(d, d["screens"][1])
    assert f"appId: {PKG}" in flow
    assert '- inputText: "qa@x.dev"' in flow
    assert "hideKeyboard" not in flow  # on Android it presses Back
    assert f'- tapOn: {{ id: "{PKG}:id/submit" }}' in flow
    assert '- assertVisible: "Home"' in flow
    flow3 = maestro_flow(d, d["screens"][2])
    assert "scrollUntilVisible" in flow3 and 'text: "Item \\\\(1\\\\)"' in flow3


def test_mermaid_escapes_ids_and_quotes():
    out = mermaid(_map_dict())
    assert out.startswith("flowchart LR")
    assert "x_com_android_chrome" in out and '"' not in out.split("-->|")[-1].split("|")[0].strip('"')
