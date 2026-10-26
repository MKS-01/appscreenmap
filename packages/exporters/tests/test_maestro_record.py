"""A recorded session becomes a Maestro flow: touches resolve to ids and labels, typing to inputText."""

from __future__ import annotations

from appscreenmap.exporters.maestro_record import FlowRecorder, TouchTracker

XML = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
 <node class="android.widget.FrameLayout" package="p" bounds="[0,0][1000,2000]" text="" resource-id="" content-desc="">
  <node class="android.widget.TextView" package="p" text="Join" resource-id="" content-desc="" bounds="[0,0][1000,200]"/>
  <node class="android.widget.Button" package="p" clickable="true" text="" resource-id="SignUp" content-desc="" bounds="[100,300][900,500]"/>
  <node class="android.widget.Button" package="p" clickable="true" text="" resource-id="" content-desc="Agree" bounds="[100,600][900,800]"/>
  <node class="android.widget.EditText" package="p" text="{name}" hint="Your name" resource-id="NameInput" content-desc="" bounds="[100,900][900,1100]"/>
  <node class="android.widget.EditText" package="p" text="{pw}" password="true" resource-id="PasswordInput" content-desc="" bounds="[100,1200][900,1400]"/>
  <node class="android.widget.ImageView" package="p" clickable="true" text="" resource-id="" content-desc="" bounds="[100,1600][300,1800]"/>
 </node>
</hierarchy>"""


def touch(tracker, x, y, t0, dur=0.05, x2=None, y2=None):
    lines = [
        f"[ {t0:.6f}] EV_ABS ABS_MT_TRACKING_ID 00000001",
        f"[ {t0:.6f}] EV_ABS ABS_MT_POSITION_X {x:08x}",
        f"[ {t0:.6f}] EV_ABS ABS_MT_POSITION_Y {y:08x}",
        f"[ {t0:.6f}] EV_KEY BTN_TOUCH DOWN",
        f"[ {t0:.6f}] EV_SYN SYN_REPORT 00000000",
    ]
    if x2 is not None:
        lines += [
            f"[ {t0 + dur / 2:.6f}] EV_ABS ABS_MT_POSITION_X {x2:08x}",
            f"[ {t0 + dur / 2:.6f}] EV_ABS ABS_MT_POSITION_Y {y2:08x}",
        ]
    lines += [
        f"[ {t0 + dur:.6f}] EV_ABS ABS_MT_TRACKING_ID ffffffff",
        f"[ {t0 + dur:.6f}] EV_KEY BTN_TOUCH UP",
    ]
    out = [g for line in lines if (g := tracker.feed(line))]
    return out[0] if out else None


def recorder(**kw):
    r = FlowRecorder("p", 1000, 2000, (1000, 2000), **kw)  # raw units equal pixels
    r.on_snapshot(XML.format(name="", pw=""))
    return r


def test_a_tap_resolves_to_the_id_then_the_label_then_a_point():
    r, t = recorder(), TouchTracker()
    r.on_gesture(touch(t, 500, 400, 1.0))
    r.on_gesture(touch(t, 500, 700, 2.0))
    r.on_gesture(touch(t, 200, 1700, 3.0))
    assert r.lines == ['- tapOn: { id: "SignUp" }', '- tapOn: "Agree"', '- tapOn: { point: "20%,85%" }']


def test_a_long_touch_is_a_long_press_and_an_edge_swipe_is_back():
    r, t = recorder(), TouchTracker()
    r.on_gesture(touch(t, 500, 400, 1.0, dur=0.9))
    r.on_gesture(touch(t, 5, 1000, 2.0, dur=0.2, x2=500, y2=1000))
    r.on_gesture(touch(t, 500, 1500, 3.0, dur=0.2, x2=500, y2=500))
    assert r.lines[0] == '- longPressOn: { id: "SignUp" }'
    assert r.lines[1] == "- back"
    assert r.lines[2] == '- swipe: { start: "50%,75%", end: "50%,25%" }'


def test_typing_becomes_input_text_and_a_password_never_reaches_the_file():
    r = recorder()
    r.on_snapshot(XML.format(name="alpha", pw=""))
    r.on_snapshot(XML.format(name="alpha b", pw="•••"))
    r.on_snapshot(XML.format(name="alpha b", pw="••••"))
    assert r.lines.count('- inputText: "alpha"') == 1
    assert '- inputText: " b"' in r.lines
    assert r.lines.count('- inputText: "${ACCOUNT_PASSWORD}"') == 1
    assert "•" not in r.render() and "-e ACCOUNT_PASSWORD" in r.render()


def test_the_hint_shown_in_an_empty_field_is_not_typing():
    r = recorder()
    r.on_snapshot(XML.format(name="Your name", pw=""))
    assert not [x for x in r.lines if x.startswith("- inputText")]


def test_the_flow_starts_with_a_launch_and_can_clear_state():
    out = recorder(clear_state=True).render()
    assert out.startswith("# Recorded") and "appId: p" in out and "    clearState: true" in out


def test_touches_on_different_input_devices_do_not_mix():
    from appscreenmap.exporters.maestro_record import MultiTouch

    m = MultiTouch()
    out = []
    for dev, x in (("/dev/input/event3", 500), ("/dev/input/event9", 100)):
        for line in (
            f"[ 1.000000] {dev}: EV_ABS ABS_MT_TRACKING_ID 00000001",
            f"[ 1.000000] {dev}: EV_ABS ABS_MT_POSITION_X {x:08x}",
            f"[ 1.000000] {dev}: EV_ABS ABS_MT_POSITION_Y 00000100",
            f"[ 1.000000] {dev}: EV_SYN SYN_REPORT 00000000",
            f"[ 1.050000] {dev}: EV_ABS ABS_MT_TRACKING_ID ffffffff\r",
        ):
            if g := m.feed(line):
                out.append(g)
    assert [g.start[0] for g in out] == [500, 100]


RN_XML = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
 <node class="android.widget.FrameLayout" package="p" bounds="[0,0][1000,2000]" text="" resource-id="" content-desc="">
  <node class="android.widget.TextView" package="p" clickable="true" text="{name}" hint="Your name" resource-id="NameInput" content-desc="" bounds="[100,900][900,1100]"/>
  <node class="android.widget.TextView" package="p" clickable="true" text="{pw}" hint="Password" resource-id="PasswordInput" content-desc="" bounds="[100,1200][900,1400]"/>
 </node>
</hierarchy>"""


def test_a_tappable_textview_with_a_hint_is_a_field_and_keyboard_taps_are_dropped():
    r, t = FlowRecorder("p", 1000, 2000, (1000, 2000)), TouchTracker()
    r.on_snapshot(RN_XML.format(name="Your name", pw="Password"))
    r.on_gesture(touch(t, 500, 1000, 1.0))
    r.on_gesture(touch(t, 300, 1800, 2.0))  # a key on the keyboard
    r.on_snapshot(RN_XML.format(name="alpha", pw="Password"))
    r.on_gesture(touch(t, 500, 1300, 3.0))
    r.on_snapshot(RN_XML.format(name="alpha", pw="12345678"))
    assert r.lines == [
        '- tapOn: { id: "NameInput" }',
        '- inputText: "alpha"',
        '- tapOn: { id: "PasswordInput" }',
        '- inputText: "${ACCOUNT_PASSWORD}"',
    ]


def test_fields_that_change_in_one_look_are_each_focused_before_typing_and_the_keyboard_is_left_alone():
    r, t = FlowRecorder("p", 1000, 2000, (1000, 2000)), TouchTracker()
    r.on_snapshot(RN_XML.format(name="Your name", pw="Password"))
    r.on_snapshot(RN_XML.format(name="alpha", pw="12345678"))
    r.on_gesture(touch(t, 500, 100, 1.0))  # a tap outside any field
    assert r.lines[:4] == [
        '- tapOn: { id: "NameInput" }',
        '- inputText: "alpha"',
        '- tapOn: { id: "PasswordInput" }',
        '- inputText: "${ACCOUNT_PASSWORD}"',
    ]
    assert not any("hideKeyboard" in x for x in r.lines)  # on Android it presses Back
