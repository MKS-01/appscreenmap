"""Serve the maps: `serve` (the web viewer, the notes and run-delete endpoints, SVG export, the activity log, manual
sessions started from the dashboard) and `mcp` (agents, over stdio)."""

from __future__ import annotations

import functools
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from appscreenmap.core import activity, manual, notes
from appscreenmap.core.model import load_map
from appscreenmap.core.runs import RunDeleteError, delete_run, resolve_run, update_index
from appscreenmap.drivers.android import AdbDriver
from appscreenmap.drivers.base import DriverError
from appscreenmap.drivers.ios import IosSimulatorDriver, user_apps
from appscreenmap.drivers.logcat import LOG as LOGS_LOG
from appscreenmap.exporters.svg import LAYOUTS, THEMES, map_svg
from appscreenmap.security import network

from . import screens
from .stack import find_canvas

_UPLOADS = threading.BoundedSemaphore(2)  # screens being uploaded at once
_SCAN = threading.Lock()  # one stack scan at a time: each pulls the app's APKs from the device
STACK_SCAN_TIMEOUT_S = 600
_PACKAGE = re.compile(r"[A-Za-z][\w]*(\.[A-Za-z_][\w]*)+")
_UDID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
_BUNDLE_ID = re.compile(r"[A-Za-z0-9][\w-]*(\.[\w-]+)+")  # iOS bundle ids may hold hyphens
_SERIAL = re.compile(r"[\w.:-]{1,64}")


def _web_dist() -> Path | None:
    candidates = [
        os.environ.get("APPSCREENMAP_WEB"),
        Path(__file__).resolve().parents[2] / "web",  # bundled in the wheel: appscreenmap/web
    ]
    candidates += [
        d / "apps" / "viewer" / "dist" for d in Path(__file__).resolve().parents
    ]  # source checkout
    for c in candidates:
        if c and (Path(c) / "index.html").is_file():
            return Path(c)
    return None


SESSION_START_WAIT_S = 8  # for `watch` to write session.json, or to fail
SESSION_STOP_WAIT_S = 20  # for `watch` to put the proxy back and tie its rows to screens


def _mark_killed(sdir: Path) -> None:
    """A `watch` that had to be killed never wrote its end: say so, or the dashboard shows it recording for ever."""
    f = sdir / "session.json"
    try:
        session = json.loads(f.read_text())
    except (OSError, ValueError):
        return
    if session.get("status") == "recording":
        session.update(
            status="failed",
            error="stopped without finishing",
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        f.write_text(json.dumps(session, indent=1) + "\n")


class _Recorder:
    """`watch` processes started from the dashboard, one at a time: a device has one proxy setting to put back."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.start_lock = threading.Lock()
        self.procs: dict[str, tuple[subprocess.Popen, Path]] = {}

    def running(self) -> dict[str, tuple[subprocess.Popen, Path]]:
        with self.lock:
            self.procs = {k: v for k, v in self.procs.items() if v[0].poll() is None}
            return dict(self.procs)

    def stop(self, sid: str) -> bool:
        with self.lock:
            proc, sdir = self.procs.pop(sid, (None, None))
        if proc is None:
            return False
        proc.terminate()  # SIGTERM: `watch` handles it like Ctrl-C
        try:
            proc.wait(SESSION_STOP_WAIT_S)
        except subprocess.TimeoutExpired:
            proc.kill()  # `doctor` reports a proxy left on the device
            proc.wait()
            _mark_killed(sdir)
        return True

    def stop_all(self) -> None:
        for sid in list(self.running()):
            self.stop(sid)


def _watch_cmd(run_dir: Path, runs_root: Path, sid: str, net: bool, serial: str | None) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "appscreenmap.engine",
        "watch",
        str(run_dir),
        "--id",
        sid,
        "--out",
        str(runs_root),
    ]
    return cmd + (["--network"] if net else []) + (["--serial", serial] if serial else [])


def _stack_cmd(
    runs_root: Path, package: str, serial: str | None, run_dir: Path | None, platform: str = "android"
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "appscreenmap.engine",
        "stack",
        "--package",
        package,
        "--out",
        str(runs_root),
        "--platform",
        platform,
        "--json",
    ]
    return cmd + (["--serial", serial] if serial else []) + ([str(run_dir)] if run_dir else [])


def _devices() -> list[dict]:
    """Attached Android devices, then booted iOS simulators. On Android, `build_type` userdebug means `adb root`
    works (what the Frida probe will need)."""
    out = []
    for serial, state in AdbDriver.list_devices():
        row: dict = {"serial": serial, "state": state, "platform": "android"}
        if state == "device":
            try:
                props = (
                    AdbDriver(serial)
                    .shell(
                        "getprop ro.boot.qemu.avd_name; getprop ro.product.model; getprop ro.build.version.sdk; "
                        "getprop ro.build.version.release; getprop ro.build.type",
                        timeout=10,
                    )
                    .splitlines()
                )
            except DriverError:
                props = []
            avd, model, sdk, release, build_type = (props + [""] * 5)[:5]
            row |= {
                "name": (avd or model).replace("_", " ") or serial,
                "api": int(sdk) if sdk.strip().isdigit() else None,
                "android": release or None,
                "build_type": build_type or None,
            }
        out.append(row)
    try:
        sims = IosSimulatorDriver.list_devices()
    except (OSError, subprocess.SubprocessError):  # no Xcode: not a Mac, or the tools aren't installed
        sims = []
    for udid, name in sims:
        model, _, release = name.partition(" · ")
        out.append(
            {"serial": udid, "state": "device", "platform": "ios", "name": model, "ios": release or None}
        )
    return out


def _installed_apps(serial: str, platform: str) -> list[str]:
    """Apps the user installed (not system apps): `pm list packages -3`, or the simulator's User apps."""
    if platform == "ios":
        return user_apps(serial)
    listing = AdbDriver(serial).shell("pm list packages -3", timeout=30)
    return sorted(
        line.removeprefix("package:").strip() for line in listing.splitlines() if line.startswith("package:")
    )


class _Handler(http.server.SimpleHTTPRequestHandler):
    runs_root: Path
    web_root: Path
    activity: activity.ActivityReader
    recorder: _Recorder
    watch_cmd = staticmethod(_watch_cmd)  # tests swap in a stand-in process
    stack_cmd = staticmethod(_stack_cmd)
    devices = staticmethod(_devices)
    installed_apps = staticmethod(_installed_apps)

    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith("/runs/"):
            rel = clean[len("/runs/") :]
            # /runs/<run-id>/… → runs/<project>/<run-id>/… (ids are flat; folders are per project)
            head, _, rest = rel.partition("/")
            if (
                head
                and not (self.runs_root / head).exists()
                and (run_dir := resolve_run(self.runs_root, head))
            ):
                rel = run_dir.relative_to(self.runs_root).as_posix() + ("/" + rest if rest else "")
            target = (self.runs_root / rel).resolve()
            if self.runs_root.resolve() not in target.parents and target != self.runs_root.resolve():
                return str(self.runs_root / "__forbidden__")
            return str(target)
        target = (self.web_root / clean.lstrip("/")).resolve()
        if not target.exists() or clean == "/":
            return str(self.web_root / "index.html")  # SPA fallback
        return str(target)

    def _run_dir(self, key: str) -> Path | None:
        """A run by `<project>/<run-id>` or by its flat id; never outside the runs folder."""
        direct = (self.runs_root / key).resolve()
        if self.runs_root.resolve() in direct.parents and (direct / "map.json").is_file():
            return direct
        return resolve_run(self.runs_root, key.rsplit("/", 1)[-1])

    def _export_svg(self) -> None:
        """GET /export/<run>.svg?layout=tree|graph|storyboard&theme=light|dark&thumbs=1: the map as one SVG file."""
        path, _, query = self.path.partition("?")
        key = unquote(path[len("/export/") :])
        opts = {k: v[0] for k, v in parse_qs(query).items()}
        layout = {"story": "storyboard"}.get(opts.get("layout", "tree"), opts.get("layout", "tree"))
        theme = opts.get("theme", "light")
        if not key.endswith(".svg") or layout not in LAYOUTS or theme not in THEMES:
            return self.send_error(400)
        run_dir = self._run_dir(key[: -len(".svg")])
        if run_dir is None:
            return self.send_error(404)
        try:
            body = map_svg(load_map(run_dir), run_dir, layout, opts.get("thumbs") != "1", theme).encode()
        except (OSError, ValueError, KeyError) as e:
            return self.send_error(422, str(e)[:100])
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Disposition", f'attachment; filename="{run_dir.name}-{layout}.svg"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
        self.wfile.write(body)

    def _json(self, data: dict, code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
        self.wfile.write(body)

    def _activity_api(self) -> None:
        """The activity log, read-only (see core/activity.py):
        GET /api/activity/live                  what is running now, and what finished in the last few seconds
        GET /api/logs/sessions?q=&source=&cmd=&run=&level=&status=&limit=   command runs that match, newest first
        GET /api/logs/session?id=&from=&q=&level=                           one command run's lines (from index `from`)
        """
        path, _, query = self.path.partition("?")
        opts = {k: v[0] for k, v in parse_qs(query).items()}
        level = opts.get("level", "")
        if level and level not in activity.LEVELS:
            return self.send_error(400, "level is info, warn or error")
        events = self.activity.events()
        if path == "/api/activity/live":
            ss = activity.sessions(events)
            return self._json(
                {
                    "has_logs": self.activity.exists(),
                    "running": [activity.summary(s) for s in reversed(ss) if s["status"] == "running"],
                    "recent": [activity.summary(s) for s in reversed(ss) if s["recent"]],
                }
            )
        if path == "/api/logs/sessions":
            try:
                limit = max(1, min(int(opts.get("limit", 100)), 500))
            except ValueError:
                return self.send_error(400, "limit is a number")
            keys = ("q", "source", "cmd", "run", "status")
            return self._json(
                activity.search(events, level=level, limit=limit, **{k: opts.get(k, "") for k in keys})
            )
        if path == "/api/logs/session":
            s = next((s for s in activity.sessions(events) if s["id"] == opts.get("id")), None)
            if s is None:
                return self.send_error(404, "no such command run")
            try:
                start = max(0, int(opts.get("from", 0)))
            except ValueError:
                return self.send_error(400, "from is a number")
            rows = [events[i] for i in s["events"][start:]]
            q = opts.get("q", "")
            return self._json(
                {
                    "session": activity.summary(s),
                    "events": [
                        {**r, "match": bool(q or level) and activity.matches(r, q, level)} for r in rows
                    ],
                    "next": len(s["events"]),
                }
            )
        return self.send_error(404)

    def _captures_api(self) -> None:
        """GET /api/captures?run=<id>: what a run recorded beyond the map: its network hosts, app log lines and manual
        `watch` sessions. The rows themselves are plain files under /runs/<id>/ (`network.jsonl`, `logs.jsonl`,
        `sessions/<id>/…`), each tagged with its `screen`.
        """
        opts = {k: v[0] for k, v in parse_qs(self.path.partition("?")[2]).items()}
        run_dir = self._run_dir(opts.get("run", "")) if opts.get("run") else None
        if run_dir is None:
            return self.send_error(404, "no such run")

        def captures(d: Path) -> dict:
            rows = network.read_log(d / network.LOG)
            logs = d / LOGS_LOG
            return {
                "network": {"log": network.LOG, **network.summarize(rows)} if rows else None,
                "logs": {"log": LOGS_LOG, "lines": sum(1 for _ in logs.open(encoding="utf-8"))}
                if logs.is_file()
                else None,
            }

        sessions = []
        for sj in sorted((run_dir / "sessions").glob("*/session.json"), reverse=True):  # ids sort by time
            try:
                s = json.loads(sj.read_text())
            except (OSError, ValueError):
                continue
            stoppable = sj.parent.name in self.recorder.running()
            sessions.append(
                {**s, **captures(sj.parent), "path": f"sessions/{sj.parent.name}", "stoppable": stoppable}
            )
        self._json({"run": run_dir.name, **captures(run_dir), "sessions": sessions})

    def do_GET(self):
        if self.path.startswith("/export/"):
            return self._export_svg()
        if self.path.split("?", 1)[0] == "/api/captures":
            return self._captures_api()
        if self.path.startswith(("/api/activity/", "/api/logs/")):
            return self._activity_api()
        if self.path.startswith("/api/devices"):
            return self._devices_api()
        if self.path.split("?", 1)[0] == "/runs/index.json":
            update_index(self.runs_root)
        super().do_GET()

    def _local_page(self) -> bool:
        """Only same-machine pages may write: the Host header guards against DNS rebinding, the Origin header against
        another site's form post (a multipart POST needs no CORS preflight)."""
        local = ("localhost", "127.0.0.1", "::1", self.server.server_address[0])
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if (origin := self.headers.get("Origin")) and (urlsplit(origin).hostname or "") not in local:
            return False
        return host in local

    def _read_json(self, limit: int = 4096) -> dict | None:
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self.send_error(415)
            return None
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if 0 < length <= limit else None
        except ValueError:
            body = None
        if not isinstance(body, dict):
            self.send_error(400, "a JSON object")
        return body if isinstance(body, dict) else None

    def do_POST(self):
        """Manual sessions from the dashboard (see `watch`), and screens filed by hand (see `add-screen`):
        POST /api/runs/<canvas>/screens  multipart: image, title, parent?, via?, scenario?, hierarchy?   201 + the screen
        POST /api/sessions  {"run": "<canvas id>", "network": true, "serial"?: "…"}   start one; 201 + its session.json
        POST /api/sessions/<id>/stop                                                stop it; 200 + its final session.json
        POST /api/stack  {"package": "…", "platform"?: "ios", "serial"?: "…", "run"?: "<canvas id>"}   scan an installed app (see `stack`);
            201 + {"run", "path", "audit"}; the canvas is found by package, or created empty
        """
        path = self.path.split("?", 1)[0]
        if m := re.fullmatch(r"/api/runs/([A-Za-z0-9_./-]{1,200})/screens", path):
            return self._add_screen(m.group(1))
        if path == "/api/stack":
            return self._scan_stack() if self._local_page() else self.send_error(403)
        if not path.startswith("/api/sessions"):
            return self.send_error(404)
        if not self._local_page():
            return self.send_error(403)
        if path == "/api/sessions":
            return self._start_session()
        m = re.fullmatch(r"/api/sessions/([A-Za-z0-9_-]{1,64})/stop", path)
        if not m:
            return self.send_error(404)
        sid = m.group(1)
        dirs = self.recorder.running()
        sdir = dirs[sid][1] if sid in dirs else None
        if sdir is None or not self.recorder.stop(sid):
            return self.send_error(404, "no session recording with that id from this dashboard")
        return self._json(json.loads((sdir / "session.json").read_text()))

    def _add_screen(self, key: str) -> None:
        if not self._local_page():
            return self.send_error(403)
        run_dir = None if ".." in key else self._run_dir(key)
        if run_dir is None:
            return self.send_error(404, "no such run")
        ctype = self.headers.get("Content-Type") or ""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.send_error(411)
        if (
            not ctype.startswith("multipart/form-data")
            or not 0 < length <= manual.MAX_IMAGE_BYTES + 3_000_000
        ):
            return self.send_error(415 if not ctype.startswith("multipart/form-data") else 413)
        if not _UPLOADS.acquire(
            timeout=20
        ):  # each upload is read whole, then parsed: a few copies of up to 23 MB
            return self._json({"error": "busy, try again"}, 503)
        try:
            f = screens.parse_multipart(ctype, self.rfile.read(length))
            text = lambda k: f[k].decode() if f.get(k) else None
            row = screens.file_screen(
                run_dir,
                f.get("image", b""),
                text("title") or "",
                parent=text("parent"),
                via=text("via"),
                scenario=text("scenario"),
                hierarchy=text("hierarchy"),
            )
        except (ValueError, TypeError, AttributeError) as e:  # ManualError is a ValueError; so is bad UTF-8
            return self._json({"error": str(e)}, 400)
        finally:
            _UPLOADS.release()
        self._json(row, 201)

    def do_PATCH(self):
        """Fix a manual screen: PATCH /api/runs/<canvas>/screens/<id>  {"title"?, "parent"?, "via"?, "scenario"?}."""
        m = re.fullmatch(r"/api/runs/([A-Za-z0-9_./-]{1,200})/screens/(s\d{3,6})", self.path.split("?", 1)[0])
        if not m:
            return self.send_error(404)
        if not self._local_page():
            return self.send_error(403)
        run_dir = None if ".." in m.group(1) else self._run_dir(m.group(1))
        if run_dir is None:
            return self.send_error(404, "no such run")
        body = self._read_json()
        if body is None:
            return
        try:
            row = screens.fix_screen(
                run_dir,
                m.group(2),
                **{k: body[k] for k in ("title", "parent", "via", "scenario") if k in body},
            )
        except (ValueError, TypeError, AttributeError) as e:
            return self._json({"error": str(e)}, 400)
        self._json(row)

    def _devices_api(self) -> None:
        """GET /api/devices: attached devices and booted simulators. GET /api/devices/<serial>/apps[?platform=ios]:
        its installed (non-system) apps, each with the canvas it already has on that platform, if any."""
        path, _, query = self.path.partition("?")
        m = re.fullmatch(r"/api/devices/([\w.:-]{1,64})/apps", path)
        # a simulator udid is a UUID; adb serials never are
        guess = "ios" if m and _UDID.fullmatch(m.group(1)) else "android"
        platform = parse_qs(query).get("platform", [guess])[0]
        if platform not in ("android", "ios"):
            return self.send_error(400, "platform")
        if path == "/api/devices":
            return self._json({"devices": self.devices()})
        if not m:
            return self.send_error(404)
        try:
            packages = self.installed_apps(m.group(1), platform)
        except (DriverError, OSError, subprocess.SubprocessError) as e:
            return self._json({"error": str(e)}, 422)
        apps = []
        for pkg in packages:
            canvas, _ = find_canvas(self.runs_root, pkg, platform)
            apps.append({"package": pkg, "run": canvas.name if canvas else None})
        self._json({"serial": m.group(1), "apps": apps})

    def _scan_stack(self) -> None:
        body = self._read_json()
        if body is None:
            return
        package, serial, run = body.get("package"), body.get("serial"), body.get("run")
        platform = body.get("platform", "android")
        if platform not in ("android", "ios"):
            return self.send_error(400, "platform")
        valid = _BUNDLE_ID if platform == "ios" else _PACKAGE
        if not (isinstance(package, str) and valid.fullmatch(package)):
            return self.send_error(400, "package")
        if serial is not None and not (isinstance(serial, str) and _SERIAL.fullmatch(serial)):
            return self.send_error(400, "serial")
        run_dir = None
        if run is not None:
            run_dir = self._run_dir(str(run))
            if run_dir is None:
                return self.send_error(404, "no such run")
        if not _SCAN.acquire(blocking=False):
            return self._json({"error": "a scan is already running"}, 409)
        try:
            proc = subprocess.run(
                self.stack_cmd(self.runs_root, package, serial, run_dir, platform),
                check=False,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=STACK_SCAN_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return self._json({"error": f"the scan took longer than {STACK_SCAN_TIMEOUT_S} s"}, 422)
        finally:
            _SCAN.release()
        if proc.returncode != 0:
            tail = proc.stderr.strip().splitlines()[-3:]
            return self._json({"error": " ".join(tail) or f"stack exited with {proc.returncode}"}, 422)
        canvas = run_dir or find_canvas(self.runs_root, package, platform)[0]
        if canvas is None:
            return self._json({"error": "the scan finished but its canvas could not be found"}, 500)
        audit = json.loads((canvas / "audits" / "stack.json").read_text())
        self._json(
            {"run": canvas.name, "path": canvas.relative_to(self.runs_root).as_posix(), "audit": audit}, 201
        )

    def _start_session(self) -> None:
        body = self._read_json()
        if body is None:
            return
        run_dir = self._run_dir(str(body.get("run") or ""))
        if run_dir is None:
            return self.send_error(404, "no such run")
        net = body.get("network", True) is not False
        if net and not network.find_mitmdump():
            return self._json({"error": f"network capture needs mitmproxy: {network.INSTALL}"}, 422)
        serial = body.get("serial")
        if serial is not None and not (isinstance(serial, str) and re.fullmatch(r"[\w.:-]{1,64}", serial)):
            return self.send_error(400, "serial")
        sid = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        sdir = run_dir / "sessions" / sid
        with (
            self.recorder.start_lock
        ):  # the check and the registration are one step: a double click starts one
            if busy := self.recorder.running():
                return self._json({"error": f"a session is already recording: {next(iter(busy))}"}, 409)
            sdir.mkdir(parents=True, exist_ok=True)
            with (sdir / "watch.log").open("w") as log:
                proc = subprocess.Popen(
                    self.watch_cmd(run_dir, self.runs_root, sid, net, serial),
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                )  # fmt: skip
            with self.recorder.lock:
                self.recorder.procs[sid] = (proc, sdir)
        deadline = time.monotonic() + SESSION_START_WAIT_S
        while time.monotonic() < deadline and proc.poll() is None and not (sdir / "session.json").is_file():
            time.sleep(0.1)
        if proc.poll() is not None and proc.returncode != 0:
            tail = (sdir / "watch.log").read_text(errors="replace").strip().splitlines()[-3:]
            return self._json(
                {"error": " ".join(tail) or f"watch exited with {proc.returncode}", "id": sid}, 422
            )
        try:
            session = json.loads((sdir / "session.json").read_text())
        except (OSError, ValueError):
            session = {"id": sid, "status": "starting"}
        self._json({**session, "path": f"sessions/{sid}", "stoppable": proc.poll() is None}, 201)

    def do_DELETE(self):
        """Delete a run from the dashboard: DELETE /runs/[<project>/]<run-id>. Refuses a crawl that is still running."""
        path = unquote(self.path.split("?", 1)[0])
        if not path.startswith("/runs/"):
            return self.send_error(404)
        if not self._local_page():
            return self.send_error(403)
        try:
            delete_run(self.runs_root, path[len("/runs/") :])
        except RunDeleteError as e:
            return self.send_error(409 if "running" in str(e) else 404, str(e))
        self.send_response(204)
        self.end_headers()

    def do_PUT(self):
        """Save viewer notes: PUT /runs/[<project>/]<run-id>/notes.json."""
        parts = self.path.split("?", 1)[0].split("/")
        run_dir = None
        if parts[:2] == ["", "runs"] and parts[-1] == notes.NOTES_FILE and len(parts) in (4, 5):
            run_dir = notes.run_dir_for(self.runs_root, parts[-2])
            if (
                run_dir
                and len(parts) == 5
                and run_dir.relative_to(self.runs_root).parts != (parts[2], parts[3])
            ):
                run_dir = None  # the project folder in the URL must be the run's real one
        if run_dir is None:
            return self.send_error(404)
        if not self._local_page():
            return self.send_error(403)
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send_error(415)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.send_error(411)
        if not 0 < length <= notes.MAX_BYTES:
            return self.send_error(413 if length else 411)
        try:
            notes.save(run_dir, self.rfile.read(length))
        except notes.NotesError as e:
            return self.send_error(400, str(e))
        self.send_response(204)
        self.end_headers()

    def end_headers(self):
        if self.path.startswith("/runs/"):
            # Screenshots keep their URL when a merge renumbers screens: the browser must ask again every time
            # (Last-Modified makes that a cheap 304), or it shows the old image under the new id.
            json_file = self.path.split("?")[0].endswith(".json")
            self.send_header("Cache-Control", "no-store" if json_file else "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):  # quiet
        pass


def cmd_serve(args) -> int:
    dist = _web_dist()
    if dist is None:
        print("Web viewer not built. Run: bun install && make viewer", file=sys.stderr)
        return 2
    runs_root = Path(args.runs).resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    update_index(runs_root)
    handler = type(
        "Handler",
        (_Handler,),
        {
            "runs_root": runs_root,
            "web_root": dist,
            "activity": activity.ActivityReader(runs_root),
            "recorder": _Recorder(),
        },
    )
    server = http.server.ThreadingHTTPServer(
        (args.host, args.port), functools.partial(handler, directory=str(dist))
    )
    url = f"http://{args.host}:{args.port}/"
    print(f"AppScreenMap viewer at {url}   (runs: {runs_root})  Ctrl+C to stop")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        handler.recorder.stop_all()  # each `watch` puts the device's proxy back before serve exits
    return 0


def cmd_mcp(args) -> int:
    try:
        from appscreenmap.engine.mcp_server import MapTools, build_server

        server = build_server(MapTools(args.runs, args.run, args.serial))
    except ImportError:
        print("The MCP server needs the mcp extra: pip install 'appscreenmap-engine[mcp]'", file=sys.stderr)
        return 2
    server.run("stdio")
    return 0


def register(sub) -> None:
    s = sub.add_parser("serve", help="open the web viewer")
    s.add_argument("--runs", default="runs")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-open", action="store_true", help="don't open a browser")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("mcp", help="serve the maps to agents over MCP (stdio)")
    s.add_argument("--runs", default="runs", help="runs directory (default: ./runs)")
    s.add_argument("--run", help="default run id (default: the latest finished run)")
    s.add_argument("--serial", help="device for where_am_i / go_to_screen / crawl")
    s.set_defaults(fn=cmd_mcp)
