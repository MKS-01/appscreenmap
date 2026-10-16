"""Follow the activity log: `logs` (what every command is doing, whoever started it: you, an agent, MCP, CI)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from appscreenmap.core import activity

_COLOURS = {"agent": "\x1b[34m", "mcp": "\x1b[36m", "ci": "\x1b[35m", "cli": "\x1b[37m"}
_LEVEL = {"warn": "\x1b[33m", "error": "\x1b[31m"}
_DIM, _RESET = "\x1b[2m", "\x1b[0m"


def matches(e: dict, args) -> bool:
    if args.run and e.get("run") != args.run:
        return False
    if args.filter_cmd and e.get("cmd") != args.filter_cmd:
        return False
    if args.source and e.get("source") != args.source:
        return False
    level = e.get("level") if e.get("level") in activity.LEVELS else "info"
    return not args.level or activity.LEVELS.index(level) >= activity.LEVELS.index(args.level)


def format_event(e: dict, colour: bool = False) -> str:
    t = (e.get("t") or "")[11:19]
    src, cmd, run = e.get("source", "cli"), e.get("cmd", "?"), e.get("run")
    where = f"{cmd} {run}" if run else cmd
    msg = e.get("msg", "")
    if not colour:
        return f"{t} [{src}] {where} · {msg}"
    tone = _LEVEL.get(e.get("level", ""), "")
    return (
        f"{_DIM}{t}{_RESET} {_COLOURS.get(src, '')}[{src}]{_RESET} {_DIM}{where} ·{_RESET} "
        f"{tone}{msg}{_RESET if tone else ''}"
    )


def cmd_logs(args) -> int:
    path = activity.stream_path(args.runs)
    events, offset = activity.read_events(path)
    if not events and not path.exists() and not args.follow:
        print(f"no activity yet: {path} is made by the first command that runs", file=sys.stderr)
        return 0
    colour = sys.stdout.isatty() and not args.json

    def show(rows: list[dict]) -> None:
        for e in rows:
            print(json.dumps(e, ensure_ascii=False) if args.json else format_event(e, colour))

    show([e for e in events if matches(e, args)][-args.lines :] if args.lines else [])
    if not args.follow:
        return 0
    try:
        while True:
            time.sleep(args.interval)
            rows, offset = activity.read_events(path, offset)
            show([e for e in rows if matches(e, args)])
    except KeyboardInterrupt:
        return 0


def register(sub) -> None:
    s = sub.add_parser(
        "logs", help="follow what every command is doing (crawls, scans, audits), whoever started it"
    )
    s.add_argument("--runs", default="runs", help="runs directory (default: ./runs)")
    s.add_argument("-n", "--lines", type=int, default=40, help="earlier events to show first (default: 40)")
    s.add_argument("--no-follow", dest="follow", action="store_false", help="print and exit")
    s.add_argument("--run", help="only this run id")
    s.add_argument("--cmd", dest="filter_cmd", help="only this command, e.g. crawl, security, a11y")
    s.add_argument("--source", choices=activity.SOURCES, help="only events from this source")
    s.add_argument("--level", choices=activity.LEVELS, help="only this level and above")
    s.add_argument("--json", action="store_true", help="one JSON event per line")
    s.add_argument("--interval", type=float, default=0.5, help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_logs)


def runs_root_for(args) -> Path | None:
    """Where this command's activity goes: its --out / --runs folder, else the runs folder its run lives in, else
    ./runs when that exists. None: there is no runs folder to log into, and none is made."""
    for name in ("out", "runs"):
        v = getattr(args, name, None)
        if isinstance(v, str):
            return Path(v)
    run = getattr(args, "run", None)
    if isinstance(run, str) and Path(run).is_dir():
        for d in Path(run).resolve().parents:
            if (d / "index.json").is_file() or (d / activity.LOGS_DIR).is_dir():
                return d
    return Path("runs") if Path("runs").is_dir() else None
