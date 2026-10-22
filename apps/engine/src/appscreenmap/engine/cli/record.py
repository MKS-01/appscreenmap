"""Record a hand-driven session as a Maestro flow: `record`.

Nothing is tapped: the touch events are read from the device and each is resolved to the element under it, so the
flow replays what was done by hand. Needs a device with a touchscreen input (an Android emulator or phone).
"""

from __future__ import annotations

import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from appscreenmap.drivers.android import AdbDriver
from appscreenmap.drivers.base import DriverError
from appscreenmap.exporters.maestro_record import FlowRecorder, MultiTouch

_DEVICE_RE = re.compile(r"add device \d+: (\S+)")
_MAX_RE = re.compile(r"ABS_MT_POSITION_([XY])\s*:.*?max (\d+)")


def touch_device(getevent_lp: str) -> tuple[str, tuple[int, int]] | None:
    """The input node that reports touch positions, and its raw (x, y) range."""
    for block in re.split(r"(?=add device )", getevent_lp):
        m = _DEVICE_RE.search(block)
        maxes = dict(_MAX_RE.findall(block))
        if m and "X" in maxes and "Y" in maxes:
            return m[1], (int(maxes["X"]), int(maxes["Y"]))
    return None


def cmd_record(args) -> int:
    d = AdbDriver(args.serial)
    found = touch_device(d.shell("getevent -lp"))
    if not found:
        print("No touchscreen input found on the device.", file=sys.stderr)
        return 2
    _, raw_max = found  # every touch node of an emulator has the same range
    width, height = d.screen_size()
    out = (
        Path(args.output)
        if args.output
        else Path(args.out) / (args.project or args.package.rsplit(".", 1)[-1]) / "maestro" / "recorded.yaml"
    )
    rec = FlowRecorder(args.package, width, height, raw_max, clear_state=args.clear_data)
    if args.clear_data:
        d.force_stop(args.package)
        d.clear_data(args.package)
    d.shell(f"monkey -p {args.package} -c android.intent.category.LAUNCHER 1")

    lock = threading.Lock()
    stop = threading.Event()

    def _terminate(signum, frame):
        stop.set()

    signal.signal(signal.SIGINT, _terminate)
    signal.signal(signal.SIGTERM, _terminate)

    def look() -> None:
        while not stop.is_set():
            try:
                snap = d.snapshot(retries=1)
            except DriverError:
                time.sleep(args.interval)
                continue
            if snap.package == args.package:
                with lock:
                    rec.on_snapshot(snap.xml)
            time.sleep(args.interval)

    watcher = threading.Thread(target=look, daemon=True)
    watcher.start()
    proc = subprocess.Popen(  # -tt: a pty keeps getevent line-buffered; no device argument reads every touch node
        [d.adb_path, "-s", d.serial, "shell", "-tt", "getevent", "-lt"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    print(f"recording {args.package} on {d.serial}: use the app; Ctrl-C to stop and save")
    deadline = time.monotonic() + args.minutes * 60 if args.minutes else None
    tracker = MultiTouch()

    def _pump() -> None:
        for line in proc.stdout:
            g = tracker.feed(line)
            if g:
                with lock:
                    rec.on_gesture(g)
                print(f"   {len(rec.lines)} step(s)", end="\r")

    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()
    try:
        while not stop.is_set() and (deadline is None or time.monotonic() < deadline):
            time.sleep(0.2)
    finally:
        stop.set()
        proc.terminate()
        reader.join(timeout=2)
        watcher.join(timeout=5)
        with lock:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(rec.render())
    print(f"\nsaved {len(rec.lines)} step(s) to {out}")
    return 0


def register(sub) -> None:
    s = sub.add_parser(
        "record",
        help="record your taps and typing on the device as a Maestro flow (ids and labels, not coordinates)",
    )
    s.add_argument("--package", required=True, help="package name of the app")
    s.add_argument("--serial", help="device serial (default: the only connected device)")
    s.add_argument(
        "--clear-data", action="store_true", help="wipe app data first, so the flow starts from first run"
    )
    s.add_argument("--interval", type=float, default=0.5, help="seconds between screen reads (default 0.5)")
    s.add_argument("--minutes", type=float, help="stop after this long (default: until Ctrl-C)")
    s.add_argument("--project", help="project folder under runs/ (default: last part of the package)")
    s.add_argument("-o", "--output", help="the flow file (default: <runs>/<project>/maestro/recorded.yaml)")
    s.add_argument("--out", default="runs", help="runs directory (default: ./runs)")
    s.set_defaults(fn=cmd_record)
