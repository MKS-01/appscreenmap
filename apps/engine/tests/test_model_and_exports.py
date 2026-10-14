from pathlib import Path

import pytest
from PIL import Image

from appscreenmap.core.analyzer import analyze
from appscreenmap.core.config import CrawlConfig
from appscreenmap.core.model import AppMap
from appscreenmap.export import maestro_flow, mermaid
from appscreenmap.testkit.helpers import PKG, compose_home, hierarchy, node
from appscreenmap.visual import compare_images

ACT = f"{PKG}.MainActivity"


def obs_of(xml):
    return analyze(xml, None, ACT, 1080, 2400)


def detail(title: str, paragraphs: int = 3):
    return hierarchy(
        node("android.widget.ImageView", (20, 150, 140, 270), desc="Back", clickable=True),
        node("android.widget.TextView", (42, 300, 1038, 420), text=title),
        *[
            node("android.widget.TextView", (42, 460 + i * 200, 1038, 640 + i * 200), text=f"p{i}")
            for i in range(paragraphs)
        ],
    )


@pytest.fixture
def amap():
    return AppMap({"id": "r1", "app": {"package": PKG}, "device": {"width": 1080, "height": 2400}})


def test_list_cap_skips_rest_when_items_lead_to_same_template(amap):
    home = amap.new_screen(obs_of(compose_home(cards=[(f"s{i}.com", f"Story {i}") for i in range(3)])), 1)
    d1 = amap.new_screen(obs_of(detail("Story 0")), 2)
    d2 = amap.new_screen(obs_of(detail("Story 1", paragraphs=4)), 3)
    cards = [e for e in home.elements.values() if e.info.kind == "list_item" and e.info.label != "MORE"]
    assert len(cards) == 3
    for el, target in zip(cards[:2], (d1, d2), strict=True):
        el.status, el.target, el.effect = "done", target.id, "new_screen"
    amap.mark_variant(d2, home, cards[1])
    assert d2.variant_of == d1.id
    amap.apply_list_cap(home, max_items=2)
    assert cards[2].status == "skipped"


def test_list_cap_keeps_going_when_items_lead_to_different_screens(amap):
    home = amap.new_screen(obs_of(compose_home(cards=[(f"s{i}.com", f"Story {i}") for i in range(3)])), 1)
    d1 = amap.new_screen(obs_of(detail("Story 0")), 2)
    settings = amap.new_screen(
        obs_of(
            hierarchy(
                node(
                    "android.widget.Switch",
                    (900, 400, 1040, 480),
                    checkable=True,
                    clickable=True,
                    text="Dark",
                )
            )
        ),
        3,
    )
    cards = [e for e in home.elements.values() if e.info.kind == "list_item" and e.info.label != "MORE"]
    for el, target in zip(cards[:2], (d1, settings), strict=True):
        el.status, el.target = "done", target.id
    amap.apply_list_cap(home, max_items=2)
    assert cards[2].status == "pending"


def test_global_nav_is_inferred(amap):
    home = amap.new_screen(obs_of(compose_home()), 1)
    following = amap.new_screen(obs_of(compose_home(greeting="Following")), 2)
    nav = next(e for e in home.elements.values() if e.info.label == "Following")
    nav.status, nav.target, nav.effect = "done", following.id, "new_screen"
    other = amap.new_screen(obs_of(compose_home(greeting="Saved")), 3)
    added = amap.infer_global_nav(other)
    inferred = next(e for e in other.elements.values() if e.info.label == "Following")
    assert inferred.status == "done" and inferred.effect == "inferred" and inferred.target == following.id
    assert added and added[0].inferred and added[0].count == 0


def test_config_inputs_and_blocking(tmp_path: Path):
    cfg = CrawlConfig()
    assert cfg.input_for("login_password") == "Passw0rd!"
    assert cfg.input_for("Email address") == "qa.tester@example.com"
    assert cfg.input_for("Postal code") == "94105"
    assert cfg.input_for("anything else") == "test"
    assert cfg.is_blocked("Sign out") and cfg.is_blocked("Delete account")
    assert not cfg.is_blocked("Settings")
    # Destructive wordings seen in real apps (sample-app's Settings has "Erase everything on this device").
    for label in ("Erase everything on this device", "Wipe data", "Reset all settings", "Clear app data"):
        assert cfg.is_blocked(label), label
    assert not cfg.is_blocked("Reset password")  # resets a password, not the device
    toml = tmp_path / "c.toml"
    toml.write_text(
        '[crawl]\nmax_steps = 10\n[inputs]\n"email" = "me@x.dev"\ndefault = "hello"\n[safety]\nblocked_text = ["archive"]\n'
    )
    cfg = CrawlConfig.load(toml, max_steps=None)
    assert cfg.max_steps == 10
    assert cfg.input_for("email") == "me@x.dev" and cfg.input_for("zzz") == "hello"
    assert cfg.is_blocked("Archive") and cfg.is_blocked("log out")
    with pytest.raises(ValueError):
        CrawlConfig.load(None, nope=1)


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
    assert f'- tapOn: {{ id: "{PKG}:id/submit" }}' in flow
    assert '- assertVisible: "Home"' in flow
    flow3 = maestro_flow(d, d["screens"][2])
    assert "scrollUntilVisible" in flow3 and 'text: "Item \\\\(1\\\\)"' in flow3


def test_mermaid_escapes_ids_and_quotes():
    out = mermaid(_map_dict())
    assert out.startswith("flowchart LR")
    assert "x_com_android_chrome" in out and '"' not in out.split("-->|")[-1].split("|")[0].strip('"')


def test_compare_images_detects_change(tmp_path: Path):
    a, b, c = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    Image.new("RGB", (100, 200), "white").save(a)
    img = Image.new("RGB", (100, 200), "white")
    img.paste((0, 0, 0), (40, 100, 60, 120))
    img.save(b)
    res = compare_images(a, b, tmp_path / "d.png", mask_top=0.05, mask_bottom=0)
    assert res["changed_ratio"] > 0 and res["bbox"] == [40, 100, 60, 120]
    Image.new("RGB", (100, 200), "white").save(c)
    assert compare_images(a, c, tmp_path / "e.png", 0.05, 0)["changed_ratio"] == 0


def test_noop_nav_item_is_inferred_as_same_screen(amap):
    home = amap.new_screen(obs_of(compose_home()), 1)
    theme = next(e for e in home.elements.values() if e.info.label == "Theme")
    theme.status, theme.effect = "done", "same_screen"
    other = amap.new_screen(obs_of(compose_home(greeting="Saved")), 2)
    amap.infer_global_nav(other)
    e = next(e for e in other.elements.values() if e.info.label == "Theme")
    assert e.status == "done" and e.effect == "same_screen" and e.target is None


def test_back_element_and_block_everywhere(amap):
    a = amap.new_screen(obs_of(compose_home()), 1)
    b = amap.new_screen(obs_of(compose_home(greeting="Other")), 2)
    amap.add_back(a)
    amap.add_back(a)
    assert [e.info.kind for e in a.elements.values()].count("back") == 1
    key = next(e.key for e in a.elements.values() if e.info.label == "Settings")
    amap.block_everywhere(key, "leaves the app")
    assert a.elements[key].status == b.elements[key].status == "blocked"
