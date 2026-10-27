"""Scanning an installed app from the dashboard: devices, their apps, and POST /api/stack. A stand-in plays `stack`."""

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
from appscreenmap.engine.cli.serve import _Handler, _Recorder

# Makes the app's canvas (zero screens) with audits/stack.json, like `stack` does for an app with no canvas.
STAND_IN = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    root, package, platform = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    if package == "dev.appscreenmap.missing":
        print(f"{package} is not installed on emulator-5554. Install it first.", file=sys.stderr)
        sys.exit(2)
    d = root / ("playground-ios" if platform == "ios" else "playground") / "playground-20261027-010000"
    (d / "audits").mkdir(parents=True, exist_ok=True)
    device = {"platform": "ios"} if platform == "ios" else {}
    run = {"id": d.name, "status": "done", "steps": 0, "app": {"package": package}, "device": device}
    (d / "map.json").write_text(json.dumps({"schema": 1, "run": run, "screens": [], "transitions": []}))
    (d / "audits" / "stack.json").write_text(json.dumps({"audit": "stack", "summary": "Native Android: Kotlin"}))
    """
)


@pytest.fixture
def dashboard(tmp_path):
    script = tmp_path / "stand_in.py"
    script.write_text(STAND_IN)
    (tmp_path / "runs").mkdir()
    attrs = {
        "runs_root": tmp_path / "runs",
        "web_root": tmp_path,
        "activity": activity.ActivityReader(tmp_path / "runs"),
        "recorder": _Recorder(),
        "stack_cmd": staticmethod(
            lambda root, package, serial, run, platform="android": [
                sys.executable,
                str(script),
                str(root),
                package,
                platform,
            ]
        ),
        "devices": staticmethod(
            lambda: [{"serial": "emulator-5554", "state": "device", "name": "Pixel 8a", "api": 37}]
        ),
        "installed_apps": staticmethod(lambda serial, platform: ["dev.appscreenmap.playground"]),
    }
    handler = type("H", (_Handler,), attrs)
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(handler, directory=str(tmp_path))
    )
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def call(method, path, body=None, origin=None):
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
        headers = {"Content-Type": "application/json"} | ({"Origin": origin} if origin else {})
        c.request(method, path, json.dumps(body) if body is not None else None, headers)
        r = c.getresponse()
        data = r.read()
        try:
            return r.status, json.loads(data)
        except ValueError:
            return r.status, data

    yield call, tmp_path / "runs"
    srv.shutdown()


def test_devices_are_listed(dashboard):
    call, _ = dashboard
    status, body = call("GET", "/api/devices")
    assert status == 200 and body["devices"][0]["serial"] == "emulator-5554"


def test_a_scan_creates_the_canvas_and_returns_its_audit(dashboard):
    call, _ = dashboard
    status, body = call(
        "POST", "/api/stack", {"package": "dev.appscreenmap.playground", "serial": "emulator-5554"}
    )
    assert status == 201
    assert (
        body["run"] == "playground-20261027-010000"
        and body["path"] == "playground/playground-20261027-010000"
    )
    assert body["audit"]["summary"] == "Native Android: Kotlin"


def test_a_failed_scan_says_why(dashboard):
    call, _ = dashboard
    status, body = call("POST", "/api/stack", {"package": "dev.appscreenmap.missing"})
    assert status == 422 and "not installed" in body["error"]


@pytest.mark.parametrize(
    "body",
    [{"package": "not a package; rm -rf"}, {"package": "dev.appscreenmap.playground", "serial": "a b"}, {}],
)
def test_bad_input_is_refused_before_anything_runs(dashboard, body):
    call, runs = dashboard
    status, _ = call("POST", "/api/stack", body)
    assert status == 400 and not any(runs.iterdir())


def test_another_site_cannot_start_a_scan(dashboard):
    call, runs = dashboard
    status, _ = call(
        "POST", "/api/stack", {"package": "dev.appscreenmap.playground"}, origin="https://evil.example"
    )
    assert status == 403 and not any(runs.iterdir())


def test_an_ios_scan_passes_the_platform_and_accepts_bundle_ids(dashboard):
    call, _ = dashboard
    status, body = call("POST", "/api/stack", {"package": "dev.appscreenmap.play-ground", "platform": "ios"})
    assert status == 201  # a hyphen is valid in a bundle id
    assert body["path"] == "playground-ios/playground-20261027-010000"  # found as the iOS canvas
    status, _ = call("POST", "/api/stack", {"package": "dev.appscreenmap.play-ground"})
    assert status == 400  # but not in an Android package name


def test_an_unknown_platform_is_refused(dashboard):
    call, runs = dashboard
    status, _ = call("POST", "/api/stack", {"package": "dev.appscreenmap.playground", "platform": "tizen"})
    assert status == 400 and not any(runs.iterdir())
    status, _ = call("GET", "/api/devices/emulator-5554/apps?platform=tizen")
    assert status == 400


def test_simulator_apps_are_listed_with_their_ios_canvas(dashboard):
    call, runs = dashboard
    d = runs / "playground-ios" / "ios-20261027-010000"
    d.mkdir(parents=True)
    run = {"id": d.name, "app": {"package": "dev.appscreenmap.playground"}, "device": {"platform": "ios"}}
    (d / "map.json").write_text(json.dumps({"run": run, "screens": []}))
    status, body = call("GET", "/api/devices/A1B2C3D4-0000-0000-0000-000000000001/apps?platform=ios")
    assert status == 200 and body["apps"] == [{"package": "dev.appscreenmap.playground", "run": d.name}]
    status, body = call("GET", "/api/devices/emulator-5554/apps")
    assert body["apps"] == [{"package": "dev.appscreenmap.playground", "run": None}]  # not the Android canvas


def test_a_simulator_udid_lists_ios_apps_without_the_platform_parameter(dashboard):
    call, runs = dashboard
    d = runs / "playground-ios" / "ios-20261027-010000"
    d.mkdir(parents=True)
    run = {"id": d.name, "app": {"package": "dev.appscreenmap.playground"}, "device": {"platform": "ios"}}
    (d / "map.json").write_text(json.dumps({"run": run, "screens": []}))
    status, body = call("GET", "/api/devices/A1B2C3D4-0000-0000-0000-000000000001/apps")
    assert status == 200 and body["apps"][0]["run"] == d.name
