"""`store`: is a build ready for Google Play's and the App Store's SDK rules, now and over the next year."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from appscreenmap.store import FORM_FACTORS, HORIZON_DAYS, android_facts, build_audit, ios_facts, write_audit


def cmd_store(args) -> int:
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
    audit = build_audit(facts, date.fromisoformat(args.today) if args.today else None, args.form_factor)
    if run:
        write_audit(run, audit)
    if args.json:
        print(json.dumps(audit, indent=1))
        return 0
    print(f"store readiness: {audit.get('status_label') or audit['status']} - {audit['summary']}")
    print("  " + ", ".join(f"{m['label']} {m['value']}" for m in audit["metrics"] if m["label"] != "note"))
    for f in audit["findings"]:
        due = f" [{f['due']}]" if f.get("due") and f["requirement"] != "met" else ""
        print(f"  {f['severity']:7} {f['requirement']:9} {f['title']}{due}")
    for m in audit["metrics"]:
        if m["label"] == "note":
            print(f"  ! {m['value']}")
    if run:
        print(f"report: {run / 'audits' / 'store.json'}  (Insights, then Store, in `appscreenmap serve`)")
    return 0


def register(sub) -> None:
    s = sub.add_parser(
        "store",
        help=f"check a build's target / compile / minimum SDK against Play and App Store rules ({HORIZON_DAYS} days ahead)",
    )
    s.add_argument("run", nargs="?", help="run folder to write audits/store.json into (optional)")
    s.add_argument("--apk", help="Android APK")
    s.add_argument("--app", help="iOS .app folder or .ipa")
    s.add_argument(
        "--form-factor",
        choices=FORM_FACTORS,
        default="phone",
        help="Android form factor (Play's target rule differs)",
    )
    s.add_argument("--today", help="evaluate as of this date (YYYY-MM-DD); default today")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_store)
