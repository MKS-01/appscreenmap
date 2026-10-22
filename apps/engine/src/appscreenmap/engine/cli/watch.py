"""Record what the app does while you use it by hand: `watch` (logs, optionally network, tied to the app's map).

Nothing is tapped: AppScreenMap only reads the screen to know where you are, follows the app's log and, with
`--network`, its traffic. The session is saved inside the app's canvas, under `sessions/<session-id>/`.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from appscreenmap.core.config import placeholders
from appscreenmap.core.model import load_map
from appscreenmap.core.runs import resolve_run, update_index
from appscreenmap.core.timeline import TIMELINE, attribute_file, write_rows
from appscreenmap.crawler.replay import Replayer, identify
from appscreenmap.drivers.android import AdbDriver
from appscreenmap.drivers.base import DriverError
from appscreenmap.drivers.logcat import LOG as LOGS_LOG
from appscreenmap.drivers.logcat import LogcatCapture
from appscreenmap.security import network
from appscreenmap.security.applogs import masker

SESSIONS = "sessions"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _latest_run_for(runs_root: Path, package: str) -> Path | None:
    try:
        index = json.loads((runs_root / "index.json").read_text())
    except (OSError, ValueError):
        return None
    for r in index.get("runs", []):  # newest first
        app = r.get("app") or {}
        if (
            app.get("package") == package
            and app.get("platform", "android") == "android"
            and r.get("status") != "running"
        ):
            d = runs_root / r["path"] if r.get("path") else resolve_run(runs_root, r["id"])
            if d and (d / "map.json").is_file():
                return d
    return None


def _secret_names(data: dict) -> list[str]:
    """The `${NAME}` inputs the crawl typed: their values, if set here, never reach the session's files."""
    cfg = data["run"].get("config") or {}
    return sorted({n for v in (cfg.get("inputs") or {}).values() for n in placeholders(str(v))})


def cmd_watch(args) -> int:
    runs_root = Path(args.out)
    if args.run:
        run_dir = Path(args.run) if Path(args.run, "map.json").is_file() else resolve_run(runs_root, args.run)
    else:
        run_dir = _latest_run_for(runs_root, args.package) if args.package else None
    if not run_dir:
        print(
            "No map to match screens against. Pass the app's canvas (run id or folder), or --package for its "
            "latest run; crawl the app first if it has none.",
            file=sys.stderr,
        )
        return 2
    data = load_map(run_dir)
    package = data["run"]["app"]["package"]
    if args.network and not network.find_mitmdump():
        print(f"--network needs mitmproxy: {network.INSTALL}", file=sys.stderr)
        return 2

    session_id = args.id or f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
        print("--id: letters, digits, - and _ only", file=sys.stderr)
        return 2
    d = AdbDriver(args.serial)
    sdir = run_dir / SESSIONS / session_id
    sdir.mkdir(parents=True, exist_ok=True)  # `serve` creates it first, for the session's watch.log
    session = {
        "id": session_id,
        "kind": "manual",
        "started_at": _now(),
        "finished_at": None,
        "status": "recording",
        "run": data["run"]["id"],
        "app": {k: data["run"]["app"].get(k) for k in ("package", "version", "label")},
        "device": d.info(),
        "logs": None if args.no_logs else {"log": LOGS_LOG, "lines": 0},
        "network": None,
        "screens": [],
    }
    (sdir / "session.json").write_text(json.dumps(session, indent=1) + "\n")

    timeline: list[dict] = []
    stack = ExitStack()
    rp = Replayer(d, data, log=lambda *a: None)
    print(
        f"watching {session['app']['label']} on {session['device'].get('name') or d.serial}: use the app; Ctrl-C to stop"
    )
    print(f"   matching screens against {data['run']['id']}; saving to {sdir}")

    def _terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _terminate)
    logs = None
    net = None
    deadline = time.monotonic() + args.minutes * 60 if args.minutes else None
    try:
        if not args.no_logs:
            logs = LogcatCapture(
                d, package, sdir / LOGS_LOG, mask=masker(os.environ.get(n) for n in _secret_names(data))
            )
            logs.start()
            stack.callback(logs.stop)
        if args.network:
            cap = network.MitmCapture(sdir / network.LOG, args.network, _secret_names(data))
            net = stack.enter_context(network.proxied(d, cap))
            session["network"] = {"mode": args.network, "tool": "mitmproxy", "log": network.LOG}
            print(f"   network: {args.network} through mitmproxy on port {net.port}")
        last = object()
        while deadline is None or time.monotonic() < deadline:
            try:
                obs = rp.observe()
            except DriverError:
                time.sleep(args.interval)
                continue
            t = time.time()
            in_app = obs.package == package
            sid, sim, _ = identify(obs, rp.app_screens) if in_app else (None, 0.0, [])
            here = (sid, obs.package if not in_app else None)
            if here != last:
                last = here
                title = rp.screens[sid].get("title") if sid else None
                entry = {"t": round(t, 3), "screen": sid, "title": title, "similarity": round(sim, 3)}
                if not in_app:
                    entry["package"] = obs.package
                elif not sid:
                    entry["activity"] = obs.activity  # in the app, but a screen the map doesn't have yet
                timeline.append(entry)
                label = (
                    f"{sid} {title}" if sid else ("not in the map" if in_app else f"outside: {obs.package}")
                )
                print(f"  {datetime.now().strftime('%H:%M:%S')}  {label}")
            time.sleep(args.interval)
        session["status"] = "done"
    except KeyboardInterrupt:
        session["status"] = "done"
    except (DriverError, network.CaptureError) as e:
        session["status"] = "failed"
        session["error"] = str(e)
        print(f"error: {e}", file=sys.stderr)
    finally:
        try:
            stack.close()  # restores the device's proxy and stops the log reader
        except DriverError as e:
            print(
                f"  ! could not put the device's proxy back ({e}): adb shell settings put global http_proxy :0"
            )
        session["finished_at"] = _now()
        write_rows(sdir / TIMELINE, timeline)
        if logs:
            session["logs"]["lines"] = len(attribute_file(sdir / LOGS_LOG, timeline))
        if session["network"]:
            attribute_file(sdir / network.LOG, timeline)
            s = network.summarize(network.read_log(sdir / network.LOG))
            session["network"].update(
                status="lost" if net and net.lost else "done",
                events=s["events"],
                hosts=len(s["hosts"]),
                cleartext_hosts=s["cleartext_hosts"],
            )
        session["screens"] = sorted({e["screen"] for e in timeline if e.get("screen")})
        (sdir / "session.json").write_text(json.dumps(session, indent=1) + "\n")
        update_index(runs_root)
    n = session["network"]
    print(
        f"\nsession saved: {len(session['screens'])} mapped screens visited"
        + (f", {session['logs']['lines']} log lines" if session["logs"] else "")
        + (f", {n.get('events', 0)} network events to {n.get('hosts', 0)} hosts" if n else "")
        + f": {sdir}"
    )
    return 0 if session["status"] == "done" else 1


def register(sub) -> None:
    s = sub.add_parser(
        "watch",
        help="record the app's logs (and, with --network, its traffic) while you use it by hand, tied to its map",
    )
    s.add_argument(
        "run", nargs="?", help="the app's canvas: run id or folder (default: --package's latest run)"
    )
    s.add_argument("--package", help="find the latest run of this package")
    s.add_argument("--serial", help="device serial (default: the only connected device)")
    s.add_argument(
        "--network",
        nargs="?",
        const="observe",
        choices=["observe"],
        help="also record the hosts the app talks to with mitmproxy (Android emulator)",
    )
    s.add_argument("--no-logs", action="store_true", help="don't record the app's log")
    s.add_argument("--interval", type=float, default=1.0, help="seconds between screen checks (default 1)")
    s.add_argument("--minutes", type=float, help="stop after this long (default: until Ctrl-C)")
    s.add_argument("--id", help="session id (default: session-<date>-<time>); `serve` passes its own")
    s.add_argument("--out", default="runs", help="runs directory (default: ./runs)")
    s.set_defaults(fn=cmd_watch)
