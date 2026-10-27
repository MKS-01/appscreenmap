"""`adaptive`: what a build's manifest or Info.plist does on foldables, tablets, desktop windows and iPhone Duo."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from appscreenmap.adaptive import android_facts, build_audit, ios_facts, write_audit


def cmd_adaptive(args) -> int:
    if bool(args.apk) == bool(args.app):
        print(
            "Pass exactly one of --apk FILE (Android) or --app FILE (iOS .app folder or .ipa).",
            file=sys.stderr,
        )
        return 2
    run = Path(args.run) if args.run else None
    if run and not (run / "map.json").is_file():
        print(f"Not a run directory (no map.json): {run}", file=sys.stderr)
        return 2
    facts = android_facts(args.apk) if args.apk else ios_facts(args.app)
    audit = build_audit(facts, args.today)
    if run:
        write_audit(run, audit)
    if args.json:
        print(json.dumps(audit, indent=1))
        return 0
    print(f"adaptive UI: {audit.get('status_label') or audit['status']} - {audit['summary']}")
    for f in audit["findings"]:
        due = f" [{f['due']}]" if f.get("due") else ""
        print(f"  {f['severity']:7} {f['title']}{due}")
        for item in (f.get("items") or [])[:5]:
            print(f"            {item}")
        if len(f.get("items") or []) > 5:
            print(f"            … {len(f['items']) - 5} more")
    n = len(audit["manual"])
    print(f"  not tested here: {n} manual check{'s' if n != 1 else ''} (listed in the report)")
    if run:
        print(f"report: {run / 'audits' / 'adaptive.json'}  (`appscreenmap report {run} --format html`)")
    return 0


def register(sub) -> None:
    s = sub.add_parser(
        "adaptive",
        help="check a build's manifest / Info.plist for orientation locks, resizing and other large-screen problems",
    )
    s.add_argument("run", nargs="?", help="run folder to write audits/adaptive.json into (optional)")
    s.add_argument("--apk", help="Android APK")
    s.add_argument("--app", help="iOS .app folder or .ipa")
    s.add_argument(
        "--today", type=date.fromisoformat, help="evaluate as of this date (YYYY-MM-DD); default today"
    )
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_adaptive)
