"""The `appscreenmap` command line: one module per command group, each registering its subcommands."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from appscreenmap.core import __version__, activity
from appscreenmap.drivers.base import DriverError

from . import analyse, crawl, logs, merge, record, screens, security, serve, store, verify, watch

GROUPS = (
    crawl,
    watch,
    record,
    verify,
    analyse,
    merge,
    screens,
    security,
    store,
    logs,
    serve,
)  # `--help` lists the commands in this order
UNLOGGED = ("serve", "mcp", "logs")  # long-running servers (MCP speaks over stdout) and the log reader itself


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="appscreenmap", description="Map every screen of a mobile app automatically."
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    for group in GROUPS:
        group.register(sub)

    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)  # progress shows up live when piped to a file
    root = None if args.cmd in UNLOGGED else logs.runs_root_for(args)
    if root is None or (not root.is_dir() and args.cmd != "crawl"):
        return _run(args)
    log = activity.ActivityLog(root, args.cmd)
    run = getattr(args, "run", None)
    if isinstance(run, str) and (Path(run) / "map.json").is_file():
        log.bind_run(run)
    log.event(" ".join(["appscreenmap", *(argv if argv is not None else sys.argv[1:])]), kind="start")
    t0, code = time.monotonic(), 1
    with activity.capture(log, sys, capture_stdout=not getattr(args, "json", False)):
        try:
            code = _run(args)
        finally:
            took = f"{time.monotonic() - t0:.1f}s"
            log.event(f"exit {code} after {took}", "info" if code == 0 else "error", kind="end", code=code)
    return code


def _run(args) -> int:
    try:
        return args.fn(args)
    except DriverError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
