"""Files under /runs/ are never served from the browser's cache without asking: a merge reuses screenshot URLs."""

from __future__ import annotations

import functools
import http.client
import http.server
import threading

import pytest

from appscreenmap.engine.cli.serve import _Handler


@pytest.fixture
def port(tmp_path):
    runs, web = tmp_path / "runs", tmp_path / "web"
    (runs / "proj" / "r1" / "screens").mkdir(parents=True)
    web.mkdir()
    (web / "index.html").write_text("<html></html>")
    (runs / "proj" / "r1" / "screens" / "s001.png").write_bytes(b"\x89PNG")
    (runs / "proj" / "r1" / "map.json").write_text("{}")
    handler = type("H", (_Handler,), {"runs_root": runs, "web_root": web})
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(handler, directory=str(tmp_path))
    )
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def cache_control(port, path):
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request("GET", path)
    r = c.getresponse()
    r.read()
    return r.status, r.getheader("Cache-Control")


def test_images_revalidate_and_json_is_never_stored(port):
    assert cache_control(port, "/runs/proj/r1/screens/s001.png") == (200, "no-cache")
    assert cache_control(port, "/runs/proj/r1/map.json") == (200, "no-store")
