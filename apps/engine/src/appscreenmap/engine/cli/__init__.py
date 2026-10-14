"""The `appscreenmap` command line: one module per command group, each registering its subcommands."""

from __future__ import annotations

import argparse
import sys

from appscreenmap.core import __version__
from appscreenmap.drivers.base import DriverError

from . import analyse, crawl, security, serve, verify

GROUPS = (crawl, verify, analyse, security, serve)  # `--help` lists the commands in this order


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
    try:
        return args.fn(args)
    except DriverError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
