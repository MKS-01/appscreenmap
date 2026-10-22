"""Starting and stopping a manual `watch` session from the dashboard. A stand-in process plays `watch`: no device."""

from __future__ import annotations

import functools
import http.client
import http.server
import json
import sys
import textwrap
import threading

import pytest

from appscreenmap.core import activity
from appscreenmap.engine.cli import serve
from appscreenmap.engine.cli.serve import _Handler, _Recorder
from appscreenmap.testkit.fakedevice import FakeDriver, crawl

# Writes session.json like `watch`, records until SIGTERM, then finishes it, as `watch` does on Ctrl-C.
STAND_IN = textwrap.dedent(
    """
    import json, signal, sys, time
    from pathlib import Path
    sdir = Path(sys.argv[1]) / "sessions" / sys.argv[2]
    doc = {"id": sys.argv[2], "kind": "manual", "status": "recording", "network": sys.argv[3] == "1"}
    (sdir / "session.json").write_text(json.dumps(doc))
    def stop(*_):
        doc["status"] = "done"
        (sdir / "session.json").write_text(json.dumps(doc))
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    while True:
        time.sleep(0.05)
    """
)


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(serve.network, "find_mitmdump", lambda: "/usr/bin/mitmdump")
    script = tmp_path / "stand_in.py"
    script.write_text(STAND_IN)
    run, _ = crawl(tmp_path / "runs", FakeDriver(), run_id="proj-20261022-100000")
    recorder = _Recorder()
    attrs = {
        "runs_root": tmp_path / "runs",
        "web_root": tmp_path,
        "activity": activity.ActivityReader(tmp_path / "runs"),
        "recorder": recorder,
        "watch_cmd": staticmethod(
            lambda run_dir, root, sid, net, serial: [
                sys.executable,
                str(script),
                str(run_dir),
                sid,
                "1" if net else "0",
            ]
        ),
    }
    handler = type("H", (_Handler,), attrs)
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(handler, directory=str(tmp_path))
    )
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def call(method, path, body=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
        headers = {"Content-Type": "application/json"} | ({"Host": host} if host else {})
        c.request(method, path, json.dumps(body) if body is not None else None, headers)
        r = c.getresponse()
        data = r.read()
        try:
            return r.status, json.loads(data)
        except ValueError:
            return r.status, data

    yield call, run, handler
    recorder.stop_all()
    srv.shutdown()


def test_start_then_stop_a_session_from_the_dashboard(dashboard):
    call, run, _ = dashboard
    status, s = call("POST", "/api/sessions", {"run": run.name})
    assert status == 201 and s["status"] == "recording" and s["network"] is True and s["stoppable"]
    assert (run / s["path"] / "watch.log").is_file()

    status, body = call("POST", "/api/sessions", {"run": run.name})  # one device, one proxy setting
    assert status == 409 and s["id"] in body["error"]

    (listed,) = call("GET", f"/api/captures?run={run.name}")[1]["sessions"]
    assert listed["id"] == s["id"] and listed["stoppable"]

    status, done = call("POST", f"/api/sessions/{s['id']}/stop")
    assert status == 200 and done["status"] == "done"
    assert call("GET", f"/api/captures?run={run.name}")[1]["sessions"][0]["stoppable"] is False
    assert call("POST", f"/api/sessions/{s['id']}/stop")[0] == 404  # already stopped


def test_logs_only_session_and_bad_requests(dashboard):
    call, run, _ = dashboard
    status, s = call("POST", "/api/sessions", {"run": run.name, "network": False})
    assert status == 201 and s["network"] is False
    call("POST", f"/api/sessions/{s['id']}/stop")
    assert call("POST", "/api/sessions", {"run": "nope"})[0] == 404
    assert call("POST", "/api/sessions", {"run": run.name, "serial": "x; rm -rf /"})[0] == 400
    assert call("POST", "/api/sessions", {"run": run.name}, host="evil.example")[0] == 403
    assert call("POST", "/api/sessions/../../stop")[0] == 404


def test_a_watch_that_fails_at_once_is_reported(dashboard, tmp_path):
    call, run, handler = dashboard
    handler.watch_cmd = staticmethod(
        lambda *a: [
            sys.executable,
            "-c",
            "import sys; print('no device connected', file=sys.stderr); sys.exit(1)",
        ]
    )
    status, body = call("POST", "/api/sessions", {"run": run.name})
    assert status == 422 and "no device connected" in body["error"]


def test_no_mitmproxy_means_no_network_session(dashboard, monkeypatch):
    call, run, _ = dashboard
    monkeypatch.setattr(serve.network, "find_mitmdump", lambda: None)
    status, body = call("POST", "/api/sessions", {"run": run.name})
    assert status == 422 and "uv tool install mitmproxy" in body["error"]
