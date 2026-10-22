"""The dashboard's entry point to a run's app logs, network hosts and manual sessions. Read-only."""

from __future__ import annotations

import functools
import http.client
import http.server
import json
import threading

from appscreenmap.core import activity
from appscreenmap.engine.cli.serve import _Handler, _Recorder
from appscreenmap.testkit.fakedevice import FakeDriver, crawl


def _get(runs, path):
    attrs = {
        "runs_root": runs,
        "web_root": runs,
        "activity": activity.ActivityReader(runs),
        "recorder": _Recorder(),
    }
    handler = type("H", (_Handler,), attrs)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(handler, directory=str(runs)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
        c.request("GET", path)
        r = c.getresponse()
        body = r.read()
        return r.status, (json.loads(body) if r.status == 200 else body)
    finally:
        srv.shutdown()


def _jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_a_run_lists_its_hosts_log_lines_and_sessions(tmp_path):
    run, _ = crawl(tmp_path, FakeDriver(), run_id="proj-20261016-120000")
    req = {"asm": 1, "event": "request", "host": "cdn.playground.test", "scheme": "http", "t": 1.0}
    _jsonl(
        run / "network.jsonl", [req, {"asm": 1, "event": "connect", "host": "api.playground.test", "t": 2.0}]
    )
    _jsonl(run / "logs.jsonl", [{"asm": 1, "event": "log", "t": 1.0, "message": "alpha"}])
    sdir = run / "sessions" / "session-20261022-100000"
    _jsonl(sdir / "logs.jsonl", [{"asm": 1, "event": "log", "t": 1.0}] * 3)
    (sdir / "session.json").write_text(json.dumps({"id": sdir.name, "kind": "manual", "screens": ["s001"]}))

    status, body = _get(tmp_path, f"/api/captures?run={run.name}")
    assert status == 200 and body["run"] == run.name
    assert [h["host"] for h in body["network"]["hosts"]] == ["api.playground.test", "cdn.playground.test"]
    assert body["network"]["cleartext_hosts"] == ["cdn.playground.test"] and body["logs"]["lines"] == 1
    (s,) = body["sessions"]
    assert s["kind"] == "manual" and s["logs"]["lines"] == 3 and s["network"] is None
    assert s["path"] == f"sessions/{sdir.name}"


def test_a_run_without_captures_says_none_and_an_unknown_run_is_404(tmp_path):
    run, _ = crawl(tmp_path, FakeDriver(), run_id="proj-20261016-120000")
    assert _get(tmp_path, f"/api/captures?run={run.name}")[1] == {
        "run": run.name,
        "network": None,
        "logs": None,
        "sessions": [],
    }
    assert _get(tmp_path, "/api/captures?run=nope")[0] == 404
