"""A playbook: scripted steps before and after the exploration (sign up with an access code, then log out last)."""

from __future__ import annotations

import json

import pytest

from appscreenmap.core import accounts
from appscreenmap.crawler import explorer as explorer_mod
from appscreenmap.testkit.fakedevice import FakeApp, FakeDriver, btn, crawl, title
from appscreenmap.testkit.helpers import PKG, hierarchy, node


def field(bounds, rid, hint):
    return node(
        "android.widget.EditText", bounds, rid=f"{PKG}:id/{rid}", hint=hint, clickable=True, focusable=True
    )


SCREENS = {
    "welcome": hierarchy(
        title("Welcome"),
        node(
            "android.widget.Button",
            (100, 300, 700, 420),
            rid=f"{PKG}:id/B2BSignUp",
            text="Join with company",
            clickable=True,
            focusable=True,
        ),
        btn((100, 500, 700, 620), text="Sign in"),
    ),
    "code": hierarchy(
        title("Create your account"),
        field((100, 300, 1000, 420), "AccessCodeInput", "Access code"),
        field((100, 460, 1000, 580), "EmailInput", "Email"),
        node(
            "android.widget.EditText",
            (100, 620, 1000, 740),
            rid=f"{PKG}:id/PasswordInput",
            hint="Password",
            password=True,
            clickable=True,
            focusable=True,
        ),
        node(
            "android.widget.Button",
            (100, 800, 700, 920),
            rid=f"{PKG}:id/ContinueButton",
            text="Continue",
            clickable=True,
            focusable=True,
        ),
    ),
    "home": hierarchy(title("Home"), btn((100, 300, 500, 420), text="Profile")),
    "profile": hierarchy(title("Profile"), btn((100, 300, 500, 420), text="Settings")),
    "settings": hierarchy(
        title("Settings"),
        node("android.widget.ScrollView", (0, 200, 1080, 2200), scrollable=True),
        btn((100, 2000, 700, 2120), text="Log out"),
    ),
    "login": hierarchy(title("Welcome back"), btn((100, 300, 500, 420), text="Sign in")),
}
NAV = {
    ("welcome", "Join with company"): "code",
    ("code", "Continue"): "home",
    ("home", "Profile"): "profile",
    ("profile", "Settings"): "settings",
    ("settings", "Log out"): "login",
}
PLAYBOOK = {
    "before": [
        {"tap": "B2BSignUp"},
        {"type": "AccessCode", "value": "ALLTABS"},
        {"type": "EmailInput", "value": "${ACCOUNT_EMAIL}"},
        {"type": "PasswordInput", "value": "${ACCOUNT_PASSWORD}"},
        {"tap": "ContinueButton"},
        {"wait": "^Home$|Profile", "timeout": 1},
        {"account": "created"},
    ],
    "after": [{"restart": True}],
}


@pytest.fixture(autouse=True)
def fast(monkeypatch, tmp_path):
    monkeypatch.setattr(explorer_mod, "PIN_TOAST_SECONDS", 0)
    monkeypatch.setattr(explorer_mod.time, "sleep", lambda s: None)
    monkeypatch.setenv("APPSCREENMAP_HOME", str(tmp_path / "home"))


def run_flow(tmp_path, monkeypatch, playbook=PLAYBOOK, **cfg):
    acct = accounts.load_or_create(PKG)
    monkeypatch.setenv("ACCOUNT_EMAIL", acct["email"])
    monkeypatch.setenv("ACCOUNT_PASSWORD", acct["password"])
    d = FakeDriver(FakeApp(SCREENS, NAV, start="welcome"))
    run_dir, _ex = crawl(tmp_path, d, playbook=playbook, max_steps=12, **cfg)
    return acct, d, run_dir, json.loads((run_dir / "map.json").read_text())


def test_before_steps_sign_up_with_the_code_and_the_saved_account(tmp_path, monkeypatch):
    acct, d, _run_dir, data = run_flow(tmp_path, monkeypatch)
    # Typed on the device: the access code, then the saved account's values (no default "test" first).
    assert d.app.typed[:3] == ["ALLTABS", acct["email"], acct["password"]]
    assert data["run"]["playbook"]["before"]["ok"] is True
    assert [s["ok"] for s in data["run"]["playbook"]["before"]["steps"]] == [True] * 7
    assert accounts.load_or_create(PKG)["status"] == "created"


def test_account_values_never_reach_the_run_folder(tmp_path, monkeypatch):
    acct, _d, run_dir, data = run_flow(tmp_path, monkeypatch)
    for f in run_dir.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".jsonl", ".yaml", ".mmd", ".xml"):
            text = f.read_text()
            assert acct["password"] not in text and acct["email"] not in text, f.name
    code = next(s for s in data["screens"] if s["title"] == "Create your account")
    values = {f["rid"].rsplit("/", 1)[-1]: (f["value"], f["secret"]) for f in code["autofill"]}
    assert values["PasswordInput"] == ("${ACCOUNT_PASSWORD}", True)
    assert values["AccessCodeInput"] == ("ALLTABS", False)


def test_after_steps_restart_reach_settings_capture_the_bottom_and_log_out_last(tmp_path, monkeypatch):
    # A logged-in app: it starts on Home. The playbook relaunches it, walks to Settings, scrolls down, logs out.
    after = {
        "after": [
            {"restart": True},
            {"tap": "^Profile$"},
            {"tap": "Settings"},
            {"scroll": "end"},
            {"tap": "Log out"},
        ]
    }
    d = FakeDriver(FakeApp(SCREENS, NAV, start="home"))
    run_dir, _ex = crawl(tmp_path, d, playbook=after, max_steps=0)
    data = json.loads((run_dir / "map.json").read_text())
    assert data["run"]["playbook"]["after"]["ok"] is True
    assert d.app.taps == ["Profile", "Settings", "Log out"] and d.app.screen == "login"
    settings = next(s for s in data["screens"] if s["title"] == "Settings")
    assert settings["captures"]["bottom"].endswith("-bottom.png")
    assert (run_dir / settings["captures"]["bottom"]).is_file()
    rows = [json.loads(line) for line in (run_dir / "trace.jsonl").read_text().splitlines()]
    assert [r["step"] for r in rows if "playbook" in r][-1] == "tap 'Log out'"


def test_the_exploration_itself_never_taps_log_out(tmp_path, monkeypatch):
    d = FakeDriver(FakeApp(SCREENS, NAV, start="home"))
    _run_dir, _ex = crawl(tmp_path, d, max_steps=30)
    assert "Log out" not in d.app.taps and "Settings" in d.app.taps


def test_a_failed_step_stops_the_phase_and_is_recorded(tmp_path, monkeypatch):
    bad = {"before": [{"tap": "B2BSignUp"}, {"tap": "NoSuchButton", "timeout": 0}, {"account": "created"}]}
    _acct, _d, _run_dir, data = run_flow(tmp_path, monkeypatch, playbook=bad)
    before = data["run"]["playbook"]["before"]
    assert before["ok"] is False and [s["ok"] for s in before["steps"]] == [True, False]
    assert accounts.load_or_create(PKG)["status"] == "new"  # the sign-up never got marked


def test_an_optional_step_may_fail(tmp_path, monkeypatch):
    pb = {"before": [{"tap": "Accept cookies", "optional": True, "timeout": 0}, {"tap": "B2BSignUp"}]}
    _acct, _d, _run_dir, data = run_flow(tmp_path, monkeypatch, playbook=pb)
    assert data["run"]["playbook"]["before"]["ok"] is True
    assert [s["ok"] for s in data["run"]["playbook"]["before"]["steps"]] == [False, True]


def test_without_a_playbook_nothing_changes(tmp_path, monkeypatch):
    _acct, _d, _run_dir, data = run_flow(tmp_path, monkeypatch, playbook={})
    assert "playbook" not in data["run"]


TABS = {
    "home": hierarchy(
        title("Home"),
        node(
            "android.widget.Button",
            (0, 2200, 360, 2400),
            rid=f"{PKG}:id/tab_home",
            text="Home",
            clickable=True,
            focusable=True,
        ),
        node(
            "android.widget.Button",
            (360, 2200, 720, 2400),
            rid=f"{PKG}:id/tab_explore",
            text="Explore",
            clickable=True,
            focusable=True,
        ),
        node(
            "android.widget.Button",
            (720, 2200, 1080, 2400),
            rid=f"{PKG}:id/tab_care",
            text="Care",
            clickable=True,
            focusable=True,
        ),
        btn((100, 300, 700, 420), text="Card one"),
        btn((100, 500, 700, 620), text="Card two"),
        btn((100, 700, 700, 820), text="Card three"),
    ),
    "card1": hierarchy(title("Card one"), btn((100, 300, 700, 420), text="Deeper")),
    "card2": hierarchy(title("Card two")),
    "card3": hierarchy(title("Card three")),
    "deeper": hierarchy(title("Deeper")),
}
for t in ("explore", "care"):
    TABS[t] = hierarchy(
        title(t.title()),
        node(
            "android.widget.Button",
            (0, 2200, 360, 2400),
            rid=f"{PKG}:id/tab_home",
            text="Home",
            clickable=True,
            focusable=True,
        ),
        node(
            "android.widget.Button",
            (360, 2200, 720, 2400),
            rid=f"{PKG}:id/tab_explore",
            text="Explore",
            clickable=True,
            focusable=True,
        ),
        node(
            "android.widget.Button",
            (720, 2200, 1080, 2400),
            rid=f"{PKG}:id/tab_care",
            text="Care",
            clickable=True,
            focusable=True,
        ),
        btn((100, 300, 700, 420), text=f"{t.title()} item A"),
        btn((100, 500, 700, 620), text=f"{t.title()} item B"),
    )
    TABS[f"{t}_a"] = hierarchy(title(f"{t.title()} item A"))
    TABS[f"{t}_b"] = hierarchy(title(f"{t.title()} item B"))
TAB_NAV = {
    ("home", "Explore"): "explore",
    ("home", "Care"): "care",
    ("explore", "Home"): "home",
    ("explore", "Care"): "care",
    ("care", "Home"): "home",
    ("care", "Explore"): "explore",
    ("home", "Card one"): "card1",
    ("home", "Card two"): "card2",
    ("home", "Card three"): "card3",
    ("card1", "Deeper"): "deeper",
    ("explore", "Explore item A"): "explore_a",
    ("explore", "Explore item B"): "explore_b",
    ("care", "Care item A"): "care_a",
    ("care", "Care item B"): "care_b",
}


def test_tab_tour_visits_every_tab_once_and_one_layer_from_each(tmp_path):
    d = FakeDriver(FakeApp(TABS, TAB_NAV, start="home"))
    run_dir, _ex = crawl(tmp_path, d, tab_tour=True, tour_taps=1, max_depth=1, max_steps=60)
    data = json.loads((run_dir / "map.json").read_text())
    titles = {s["title"] for s in data["screens"]}
    assert {"Home", "Explore", "Care"} <= titles
    # Exactly one content tap per tab screen (the first card / item), not every card.
    deeper = [t for t in titles if t.startswith(("Card", "Explore item", "Care item"))]
    assert len(deeper) == 3 and "Deeper" not in titles  # one per tab, and no second layer (max_depth = 1)


def test_without_the_tour_the_same_app_is_explored_fully(tmp_path):
    d = FakeDriver(FakeApp(TABS, TAB_NAV, start="home"))
    run_dir, _ex = crawl(tmp_path, d, max_steps=80)
    titles = {s["title"] for s in json.loads((run_dir / "map.json").read_text())["screens"]}
    assert {"Card one", "Card two", "Card three", "Deeper"} <= titles


def test_type_finds_a_field_that_is_not_a_plain_text_input(tmp_path, monkeypatch):
    # Some apps draw their text fields as clickable TextViews (no EditText): `type` still finds them by id or label.
    custom = {
        "start": hierarchy(
            title("Code"),
            node(
                "android.widget.TextView",
                (100, 300, 1000, 420),
                rid=f"{PKG}:id/AccessCodeInput",
                text="Enter code",
                clickable=True,
                focusable=True,
            ),
        )
    }
    d = FakeDriver(FakeApp(custom, {}, start="start"))
    _run_dir, _ex = crawl(
        tmp_path, d, playbook={"before": [{"type": "AccessCodeInput", "value": "ALLTABS"}]}, max_steps=0
    )
    assert d.app.typed == ["ALLTABS"]


def test_tap_at_taps_a_screen_fraction_where_no_node_is_clickable(tmp_path):
    d = FakeDriver(FakeApp(SCREENS, NAV, start="welcome"))
    # "Join with company" spans x 100-700, y 300-420 of the 1080x2400 fake screen: (0.3, 0.15) is inside it.
    _run_dir, _ex = crawl(tmp_path, d, playbook={"before": [{"tap_at": [0.3, 0.15]}]}, max_steps=0)
    assert d.app.taps == ["Join with company"]


def test_tap_at_needs_two_fractions():
    from appscreenmap.core.config import validate_playbook

    with pytest.raises(ValueError, match="fractions"):
        validate_playbook({"before": [{"tap_at": [300, 900]}]})


def test_playbook_tap_at_and_back_leave_arrows_on_the_map(tmp_path):
    d = FakeDriver(FakeApp(SCREENS, NAV, start="welcome"))
    playbook = {"before": [{"tap_at": [0.3, 0.15]}, {"back": True}]}
    run_dir, _ex = crawl(tmp_path, d, playbook=playbook, max_steps=0)
    m = json.loads((run_dir / "map.json").read_text())
    arrows = [(t["from"], t["to"], t["kind"]) for t in m["transitions"]]
    assert len(arrows) == 2  # welcome -> code (tap at), code -> welcome (back)
    assert arrows[0][2] == "link" and arrows[1][2] == "back"
    assert arrows[0][:2] == arrows[1][:2][::-1]


FLIP_AFTER = 3


def test_screen_the_app_moves_to_by_itself_joins_the_tree(tmp_path):
    # "welcome" -> "code" happens with no tap (a carousel advancing) while the playbook waits for a field on "code".
    app = FakeApp(SCREENS, NAV, start="welcome")
    d = FakeDriver(app)
    real, seen = d.snapshot, []

    def snapshot(retries=3):
        seen.append(app.screen)
        if len(seen) > FLIP_AFTER:
            app.screen = "code"
        return real(retries)

    d.snapshot = snapshot
    run_dir, _ex = crawl(
        tmp_path, d, playbook={"before": [{"wait": "AccessCodeInput", "timeout": 5}]}, max_steps=0
    )
    m = json.loads((run_dir / "map.json").read_text())
    assert [t["kind"] for t in m["transitions"]] == ["auto"]
    code = next(s for s in m["screens"] if s["title"] == "Create your account")
    assert code["origin"] == "action" and code["depth"] == 1


def test_entry_step_makes_the_current_screen_another_entry_point(tmp_path):
    d = FakeDriver(FakeApp(SCREENS, NAV, start="welcome"))
    playbook = {
        "before": [{"tap": "B2BSignUp"}, {"entry": True}, {"tap": "ContinueButton", "optional": True}]
    }
    run_dir, _ex = crawl(tmp_path, d, playbook=playbook, max_steps=0)
    m = json.loads((run_dir / "map.json").read_text())
    code = next(s for s in m["screens"] if s["title"] == "Create your account")
    assert (code["origin"], code["depth"], code["reach_path"]) == ("launch", 0, [])


def test_entry_must_be_true():
    from appscreenmap.core.config import validate_playbook

    with pytest.raises(ValueError, match="entry"):
        validate_playbook({"before": [{"entry": "yes"}]})


def test_bottom_tabs_hang_off_the_tab_root_and_are_named_after_the_tab(tmp_path):
    def tabs(selected):
        bar = [
            node(
                "android.widget.Button",
                (i * 270, 2200, i * 270 + 270, 2400),
                text=t,
                clickable=True,
                selected=(t == selected),
            )
            for i, t in enumerate(["Home", "Explore", "Care", "Me"])
        ]
        return bar

    screens = {
        "home": hierarchy(title("Hello, QA"), *tabs("Home")),
        "explore": hierarchy(
            title("Explore feed"),
            btn((100, 300, 500, 420), text="Search"),
            btn((100, 500, 500, 620), text="Topics"),
            btn((100, 700, 500, 820), text="Saved"),
            *tabs("Explore"),
        ),
        "care": hierarchy(
            title("Care team"),
            btn((100, 300, 500, 420), text="Book a coach"),
            btn((100, 500, 500, 620), text="Messages"),
            btn((100, 700, 500, 820), text="Crisis line"),
            *tabs("Care"),
        ),
    }
    nav = {("home", "Explore"): "explore", ("explore", "Care"): "care"}
    d = FakeDriver(FakeApp(screens, nav, start="home"))
    run_dir, _ex = crawl(
        tmp_path, d, playbook={"before": [{"tap": "^Explore$"}, {"tap": "^Care$"}]}, max_steps=0
    )
    m = json.loads((run_dir / "map.json").read_text())
    by = {s["title"]: s for s in m["screens"]}
    assert set(by) == {"Home", "Explore", "Care"}
    assert [x["screen"] for x in by["Care"]["reach_path"]] == [by["Home"]["id"]]
    assert by["Care"]["depth"] == by["Explore"]["depth"]
