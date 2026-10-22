"""`watch` records a hand-driven session inside the app's canvas, tapping nothing."""

from __future__ import annotations

import json

from appscreenmap.engine.cli import main, watch
from appscreenmap.testkit.fakedevice import FakeDriver, crawl


def test_a_session_is_saved_in_the_canvas_with_the_screens_visited(tmp_path, monkeypatch):
    d = FakeDriver()
    run, _ = crawl(tmp_path, d, run_id="proj-20261016-120000")
    (tmp_path / "index.json").write_text('{"runs": []}')
    monkeypatch.setattr(watch, "AdbDriver", lambda serial: d)
    taps = list(d.app.taps)
    assert main(["watch", str(run), "--minutes", "0.002", "--interval", "0.01", "--out", str(tmp_path)]) == 0
    (sdir,) = (run / watch.SESSIONS).iterdir()
    session = json.loads((sdir / "session.json").read_text())
    assert session["status"] == "done" and session["kind"] == "manual" and session["run"] == run.name
    timeline = [json.loads(x) for x in (sdir / "timeline.jsonl").read_text().splitlines()]
    assert timeline[0]["title"] == "Home" and session["screens"] == [timeline[0]["screen"]]
    assert d.app.taps == taps and d.http_proxy == ""
