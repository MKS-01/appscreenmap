"""`add-screen` / `edit-screen` and the dashboard endpoints: a screen filed by hand lands on the canvas, takes part in
the derived files, and a fix rewrites them."""

from __future__ import annotations

import functools
import http.client
import http.server
import io
import json
import threading

import pytest
from PIL import Image

from appscreenmap.engine.cli import main
from appscreenmap.engine.cli.serve import _Handler
from appscreenmap.testkit.fakedevice import FakeDriver, crawl


def png_bytes():
    out = io.BytesIO()
    Image.new("RGB", (120, 240), "white").save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def canvas(tmp_path):
    run, _ = crawl(tmp_path, FakeDriver(), run_id="canvas")
    return run


def screens_of(run):
    return json.loads((run / "map.json").read_text())["screens"]


def test_add_screen_cli_files_it_and_refreshes_the_derived_files(canvas, tmp_path):
    img = tmp_path / "support.png"
    img.write_bytes(png_bytes())
    parent = screens_of(canvas)[0]["id"]
    before = len(screens_of(canvas))
    flows_before = {p.name for p in (canvas / "flows").glob("*.yaml")}

    rc = main(["add-screen", str(canvas), "--image", str(img), "--title", "Support", "--from", parent])
    assert rc == 0

    rows = screens_of(canvas)
    new = (
        rows[-1]
        if rows[-1].get("source") == "manual"
        else next(s for s in rows if s.get("source") == "manual")
    )
    assert len(rows) == before + 1 and new["title"] == "Support"
    assert (canvas / new["screenshot"]).is_file()
    assert {p.name for p in (canvas / "flows").glob("*.yaml")} >= flows_before  # exports re-ran, nothing lost
    assert (canvas / "a11y.json").is_file()


def test_edit_screen_cli_and_a_crawled_screen_is_refused(canvas, tmp_path, capsys):
    img = tmp_path / "s.png"
    img.write_bytes(png_bytes())
    main(["add-screen", str(canvas), "--image", str(img), "--title", "Before"])
    sid = next(s["id"] for s in screens_of(canvas) if s.get("source") == "manual")
    assert main(["edit-screen", str(canvas), sid, "--title", "After"]) == 0
    assert next(s for s in screens_of(canvas) if s["id"] == sid)["title"] == "After"
    crawled = next(s["id"] for s in screens_of(canvas) if s.get("source") != "manual" and s["kind"] == "app")
    assert main(["edit-screen", str(canvas), crawled, "--title", "No"]) == 2
    assert "crawled" in capsys.readouterr().err


@pytest.fixture
def server(tmp_path):
    runs = tmp_path / "runs"
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html></html>")
    run, _ = crawl(runs, FakeDriver(), run_id="canvas")  # runs/proj/canvas
    handler = type("H", (_Handler,), {"runs_root": runs, "web_root": web})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(handler, directory=str(web)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield run, srv.server_address[1]
    srv.shutdown()


def multipart(fields: dict[str, bytes]):
    b = "XBOUNDARYX"
    body = b""
    for k, v in fields.items():
        fn = '; filename="s.png"' if k == "image" else ""
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"{fn}\r\n\r\n'.encode() + v + b"\r\n"
    return body + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def call(port, method, path, body=b"", ctype="application/json", host="127.0.0.1"):
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request(method, path, body=body, headers={"Host": host, "Content-Type": ctype})
    r = c.getresponse()
    return r.status, r.read()


def test_post_files_a_screen_and_patch_fixes_it(server):
    run, port = server
    body, ctype = multipart({"image": png_bytes(), "title": b"Support"})
    status, out = call(port, "POST", "/api/runs/proj/canvas/screens", body, ctype)
    assert status == 201
    row = json.loads(out)
    assert row["source"] == "manual" and (run / row["screenshot"]).is_file()

    status, out = call(
        port, "PATCH", f"/api/runs/proj/canvas/screens/{row['id']}", json.dumps({"title": "Help"}).encode()
    )
    assert status == 200 and json.loads(out)["title"] == "Help"


def test_post_refuses_bad_images_strangers_and_other_hosts(server):
    run, port = server
    before = (run / "map.json").read_text()
    body, ctype = multipart({"image": b"nope", "title": b"X"})
    assert call(port, "POST", "/api/runs/proj/canvas/screens", body, ctype)[0] == 400
    ok, ctype = multipart({"image": png_bytes(), "title": b"X"})
    assert call(port, "POST", "/api/runs/proj/canvas/screens", ok, ctype, host="evil.example")[0] == 403
    assert call(port, "POST", "/api/runs/proj/missing/screens", ok, ctype)[0] == 404
    assert call(port, "POST", "/api/runs/proj/canvas/screens", b"{}", "application/json")[0] == 415
    assert (run / "map.json").read_text() == before


def test_a_manual_screen_is_found_and_listed_by_the_agent_tools(canvas, tmp_path):
    from appscreenmap.engine.mcp_server import MapTools

    img = tmp_path / "s.png"
    img.write_bytes(png_bytes())
    main(["add-screen", str(canvas), "--image", str(img), "--title", "Second consent"])
    tools = MapTools(canvas.parent.parent)
    hit = tools.find_screens("second consent", run=canvas.name)["screens"][0]
    assert hit["title"] == "Second consent"
    shown = tools.get_screen(hit["id"], run=canvas.name)
    assert shown["how_to_reach"] == ["no recorded path"]  # honest: nothing replayable yet
    assert hit["id"] in json.dumps(tools.list_screens(run=canvas.name))


def test_edit_screen_cli_replaces_the_image(canvas, tmp_path):
    first, second = tmp_path / "a.png", tmp_path / "b.png"
    first.write_bytes(png_bytes())
    Image.new("RGB", (60, 90), "black").save(second, "PNG")
    main(["add-screen", str(canvas), "--image", str(first), "--title", "Page"])
    row = next(s for s in screens_of(canvas) if s.get("source") == "manual")
    assert main(["edit-screen", str(canvas), row["id"], "--image", str(second)]) == 0
    assert (canvas / row["screenshot"]).read_bytes() == second.read_bytes()
    assert next(s for s in screens_of(canvas) if s["id"] == row["id"])["width"] == 60


def test_bad_types_and_paths_are_a_clean_400_or_404(server):
    _, port = server
    body, ctype = multipart({"image": png_bytes(), "title": b"Page"})
    sid = json.loads(call(port, "POST", "/api/runs/proj/canvas/screens", body, ctype)[1])["id"]
    path = f"/api/runs/proj/canvas/screens/{sid}"
    for bad in ({"scenario": ["a"]}, {"via": 5, "parent": "s001"}, {"title": 7}, {"parent": sid}):
        status, out = call(port, "PATCH", path, json.dumps(bad).encode())
        assert status == 400 and "error" in json.loads(out), bad
    assert call(port, "PATCH", "/api/runs/../../canvas/screens/s001", b"{}")[0] == 404
    assert call(port, "POST", "/api/runs/../../canvas/screens", body, ctype)[0] == 404
    assert call(port, "PATCH", path, json.dumps({"title": "Still fine"}).encode())[0] == 200
