from appscreenmap.core.timeline import attribute


def test_rows_take_the_screen_showing_when_they_started():
    timeline = [
        {"t": 10.0, "screen": "s001", "title": "Home"},
        {"t": 20.0, "screen": None},  # the app went to the background
        {"t": 30.0, "screen": "s004", "title": "Profile"},
    ]
    rows = [{"t": 5.0}, {"t": 10.0}, {"t": 25.0}, {"t": 31.5}, {"x": 1}]
    got = attribute(rows, timeline)
    assert [r.get("screen", "-") for r in got] == ["-", "s001", None, "s004", "-"]
    assert got[3]["screen_title"] == "Profile"
    assert rows[1] == {"t": 10.0}  # inputs are not changed
