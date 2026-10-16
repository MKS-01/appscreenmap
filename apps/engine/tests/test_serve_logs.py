"""The dashboard's activity endpoints: what runs now, command runs to search, one run's lines. Read-only."""

from __future__ import annotations

import functools
import http.client
import http.server
import json
import os
import threading

import pytest

from appscreenmap.core import activity
from appscreenmap.engine.cli.serve import _Handler


@pytest.fixture
def server(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html></html>")
    attrs = {"runs_root": runs, "web_root": web, "activity": activity.ActivityReader(runs)}
    handler = type("H", (_Handler,), attrs)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(handler, directory=str(web)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield runs, srv.server_address[1]
    srv.shutdown()


def get(port, path):
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request("GET", path)
    r = c.getresponse()
    body = r.read()
    return r.status, (json.loads(body) if r.status == 200 else body)


def test_no_log_yet(server):
    _, port = server
    assert get(port, "/api/activity/live") == (200, {"has_logs": False, "running": [], "recent": []})
    assert get(port, "/api/logs/sessions")[1] == {"sessions": [], "total": 0}


def test_live_search_and_one_run(server):
    runs, port = server
    done = activity.ActivityLog(runs, "security", source="cli", env={})
    done.pid = 999_999_999  # no such process: once ended it is just history
    done.event("appscreenmap security", kind="start")
    done.line("! cleartext traffic allowed", "stdout")
    done.event("exit 0 after 0.1s", kind="end", code=0)
    live = activity.ActivityLog(runs, "crawl", source="agent", env={})  # this test's own pid: alive
    live.event("appscreenmap crawl", kind="start")
    live.line("new screen Settings")

    _, body = get(port, "/api/activity/live")
    assert body["has_logs"] and [s["cmd"] for s in body["running"]] == ["crawl"]
    assert body["running"][0]["pid"] == os.getpid() and body["running"][0]["last"] == "new screen Settings"
    assert [s["cmd"] for s in body["recent"]] == ["security"]

    _, found = get(port, "/api/logs/sessions?q=cleartext")
    assert [s["cmd"] for s in found["sessions"]] == ["security"] and found["sessions"][0]["exit"] == 0
    assert get(port, "/api/logs/sessions?level=warn")[1]["total"] == 1
    assert get(port, "/api/logs/sessions?source=agent")[1]["sessions"][0]["status"] == "running"

    sid = body["running"][0]["id"]
    _, one = get(port, f"/api/logs/session?id={sid}")
    assert [e["msg"] for e in one["events"]] == ["appscreenmap crawl", "new screen Settings"]
    live.line("new screen About")
    _, more = get(port, f"/api/logs/session?id={sid}&from={one['next']}&q=about")
    assert [(e["msg"], e["match"]) for e in more["events"]] == [("new screen About", True)]


def test_bad_queries(server):
    _, port = server
    assert get(port, "/api/logs/sessions?level=loud")[0] == 400
    assert get(port, "/api/logs/sessions?limit=many")[0] == 400
    assert get(port, "/api/logs/session?id=nope")[0] == 404
    assert get(port, "/api/logs/nothing")[0] == 404
