"""`GET /export/<run>.svg` on the dashboard server."""

from __future__ import annotations

import functools
import http.client
import http.server
import json
import threading

import pytest

from appscreenmap.engine.cli.serve import _Handler

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63f8cfc0f01f0005850180ac3b86"
    "230000000049454e44ae426082"
)


@pytest.fixture
def server(tmp_path):
    run = tmp_path / "runs" / "demo" / "demo-1"
    (run / "screens").mkdir(parents=True)
    (run / "screens" / "s001.png").write_bytes(PNG)
    (run / "map.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "run": {"id": "demo-1", "app": {"label": "Demo", "package": "x"}},
                "screens": [
                    {
                        "id": "s001",
                        "kind": "app",
                        "title": "Home",
                        "depth": 0,
                        "first_step": 1,
                        "width": 100,
                        "height": 200,
                        "screenshot": "screens/s001.png",
                        "thumb": "screens/s001.png",
                    }
                ],
                "transitions": [],
            }
        )
    )
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html></html>")
    handler = type("H", (_Handler,), {"runs_root": tmp_path / "runs", "web_root": web})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(handler, directory=str(web)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def get(port, path):
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request("GET", path)
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_export_by_project_path_or_flat_id_downloads_an_svg(server):
    for key in ("demo/demo-1", "demo-1"):
        status, headers, body = get(server, f"/export/{key}.svg?layout=story")
        assert status == 200 and headers["Content-Type"] == "image/svg+xml"
        assert headers["Content-Disposition"] == 'attachment; filename="demo-1-storyboard.svg"'
        assert body.startswith(b"<svg") and b"Home" in body


def test_bad_requests_are_refused(server):
    assert get(server, "/export/demo-1.svg?layout=radial")[0] == 400
    assert get(server, "/export/demo-1.svg?theme=neon")[0] == 400
    assert get(server, "/export/demo-1")[0] == 400
    assert get(server, "/export/nope.svg")[0] == 404
    assert get(server, "/export/..%2F..%2Fetc.svg")[0] == 404
