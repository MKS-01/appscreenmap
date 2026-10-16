"""`DELETE /runs/<run>` on the dashboard server: removes one run folder, never anything else."""

from __future__ import annotations

import functools
import http.client
import http.server
import json
import threading

import pytest

from appscreenmap.core.runs import RunDeleteError, delete_run
from appscreenmap.engine.cli.serve import _Handler


def make_run(runs, project, run_id, status="done"):
    d = runs / project / run_id
    d.mkdir(parents=True)
    (d / "map.json").write_text(
        json.dumps(
            {"schema": 1, "run": {"id": run_id, "status": status, "app": {"package": "x"}}, "screens": []}
        )
    )
    return d


@pytest.fixture
def server(tmp_path):
    runs = tmp_path / "runs"
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html></html>")
    handler = type("H", (_Handler,), {"runs_root": runs, "web_root": web})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(handler, directory=str(web)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield runs, srv.server_address[1]
    srv.shutdown()


def delete(port, path, host="127.0.0.1"):
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request("DELETE", path, headers={"Host": host})
    return c.getresponse().status


def test_delete_by_project_path_or_flat_id(server):
    runs, port = server
    a = make_run(runs, "demo", "demo-1")
    b = make_run(runs, "demo", "demo-2")
    keep = make_run(runs, "demo", "demo-3")
    assert delete(port, "/runs/demo/demo-1") == 204 and not a.exists()
    assert delete(port, "/runs/demo-2") == 204 and not b.exists()
    assert keep.exists()
    index = json.loads((runs / "index.json").read_text())
    assert [r["id"] for r in index["runs"]] == ["demo-3"]


def test_delete_refuses_running_crawls_strangers_and_paths_outside(server, tmp_path):
    runs, port = server
    live = make_run(runs, "demo", "demo-live", status="running")
    outside = make_run(tmp_path, "elsewhere", "victim")
    assert delete(port, "/runs/demo/demo-live") == 409 and live.exists()
    assert delete(port, "/runs/demo/demo-live", host="evil.example") == 403
    assert delete(port, "/runs/..%2Felsewhere%2Fvictim") == 404 and outside.exists()
    assert delete(port, "/runs/demo") == 404 and (runs / "demo").exists()  # a project folder is not a run
    assert delete(port, "/runs/nope") == 404


def test_delete_run_needs_a_run_folder(tmp_path):
    runs = tmp_path / "runs"
    make_run(runs, "demo", "demo-1")
    with pytest.raises(RunDeleteError):
        delete_run(runs, "demo/../demo/demo-1")
    with pytest.raises(RunDeleteError):
        delete_run(runs, "")
