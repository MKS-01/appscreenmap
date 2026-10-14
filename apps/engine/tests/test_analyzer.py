from helpers import PKG, compose_home, hierarchy, node

from appscreenmap.analyzer import analyze, is_crash_dialog, is_permission_dialog, jaccard

ACT = f"{PKG}.MainActivity"


def run(xml, **kw):
    return analyze(xml, None, ACT, 1080, 2400, **kw)


def by_label(obs):
    return {e.label: e for e in obs.elements}


def test_compose_leaves_are_not_list_items():
    els = by_label(run(compose_home()))
    assert els["Settings"].kind == "button"
    assert els["15 MIN"].kind == "button"


def test_cards_are_a_list_group_and_nested_buttons_get_their_own_group():
    obs = run(compose_home())
    cards = [e for e in obs.elements if e.kind == "list_item" and e.label != "MORE"]
    more = [e for e in obs.elements if e.label == "MORE"]
    assert len(cards) == 2 and cards[0].group == cards[1].group
    assert more and more[0].group != cards[0].group
    assert "list" in obs.patterns


def test_colliding_normalized_labels_get_ordinals():
    keys = [e.key for e in run(compose_home()).elements if e.label.endswith("MIN")]
    assert len(keys) == 3 and len(set(keys)) == 3


def test_bottom_nav_detected():
    obs = run(compose_home())
    nav = [e for e in obs.elements if e.kind == "nav"]
    assert {e.label for e in nav} == {"Home", "Following", "Saved", "Theme"}
    assert next(e for e in nav if e.label == "Home").selected
    assert "bottom_nav" in obs.patterns


def test_signature_ignores_feed_content_and_digits():
    a = run(compose_home(cards=(("a.com", "Story A"), ("b.com", "Story B"))))
    b = run(compose_home(cards=(("c.com", "Story C"), ("d.com", "Story D"))))
    assert a.signature == b.signature
    t1 = run(compose_home(greeting="Updated 10:15"))
    t2 = run(compose_home(greeting="Updated 11:42"))
    assert t1.signature == t2.signature


def test_different_screens_differ():
    home = run(compose_home())
    settings = run(
        hierarchy(
            node("android.widget.TextView", (42, 200, 600, 260), text="Settings"),
            node("android.widget.ImageView", (931, 166, 1057, 292), desc="Close settings", clickable=True),
            node(
                "android.widget.Switch",
                (900, 400, 1040, 480),
                checkable=True,
                clickable=True,
                text="Dark mode",
            ),
        )
    )
    assert home.signature != settings.signature
    assert jaccard(home.tokens, settings.tokens) < 0.5
    assert by_label(settings)["Dark mode"].kind == "toggle"


def test_scroll_key_is_stable_when_content_scrolls():
    k1 = next(e.key for e in run(compose_home()).elements if e.action == "scroll")
    k2 = next(e.key for e in run(compose_home(greeting="Other text")).elements if e.action == "scroll")
    assert k1 == k2


def test_keypad_grid_is_grouped():
    keys = [
        node(
            "android.widget.Button",
            (100 + (i % 3) * 300, 800 + (i // 3) * 200, 380 + (i % 3) * 300, 980 + (i // 3) * 200),
            text=str(i),
            rid=f"{PKG}:id/digit_{i}",
            clickable=True,
        )
        for i in range(10)
    ]
    obs = run(hierarchy(node(bounds=(0, 700, 1080, 1900), children=keys)))
    digits = [e for e in obs.elements if e.text.isdigit()]
    assert len(digits) == 10
    assert all(e.kind == "list_item" for e in digits)
    assert len({e.group for e in digits}) == 1


def test_inputs_title_and_login_pattern():
    obs = run(
        hierarchy(
            node("android.widget.TextView", (42, 200, 600, 260), text="Sign in", rid=f"{PKG}:id/title"),
            node("android.widget.EditText", (42, 400, 1038, 520), hint="Email", focusable=True),
            node(
                "android.widget.EditText",
                (42, 560, 1038, 680),
                hint="Password",
                password=True,
                focusable=True,
            ),
            node("android.widget.Button", (42, 760, 1038, 880), text="Log out", clickable=True),
        ),
        is_blocked=lambda label: "log out" in label.lower(),
    )
    assert obs.title == "Sign in"
    assert {"form", "login"} <= set(obs.patterns)
    assert by_label(obs)["Log out"].blocked


def test_huge_click_targets_are_ignored():
    obs = run(hierarchy(node(bounds=(0, 0, 1080, 2400), clickable=True)))
    assert not [e for e in obs.elements if e.action == "click"]


def test_listview_rows_are_implicitly_clickable():
    rows = [
        node(
            "android.widget.LinearLayout",
            (500, 300 + i * 120, 1050, 420 + i * 120),
            children=[node("android.widget.TextView", (540, 330 + i * 120, 1000, 390 + i * 120), text=t)],
        )
        for i, t in enumerate(["Settings", "Help", "About"])
    ]
    obs = run(hierarchy(node("android.widget.ListView", (500, 300, 1050, 660), children=rows)))
    assert {e.label for e in obs.elements if e.action == "click"} == {"Settings", "Help", "About"}


def test_system_dialog_detection():
    perm = analyze(
        hierarchy(
            node(
                "android.widget.Button",
                (100, 1500, 980, 1600),
                text="Allow",
                rid="com.android.permissioncontroller:id/permission_allow_button",
                clickable=True,
                package="com.android.permissioncontroller",
            )
        ).replace(f'package="{PKG}"', 'package="com.android.permissioncontroller"'),
        None,
        None,
        1080,
        2400,
    )
    assert is_permission_dialog(perm)
    crash = analyze(
        hierarchy(node("android.widget.TextView", (100, 1000, 980, 1100), text="App keeps stopping")).replace(
            f'package="{PKG}"', 'package="android"'
        ),
        None,
        None,
        1080,
        2400,
    )
    assert is_crash_dialog(crash)
