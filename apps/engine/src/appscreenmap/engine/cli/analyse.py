"""Read a finished run: `report` (crawl health), `perf`, `a11y`."""

from __future__ import annotations

import json

from appscreenmap.a11y.checks import audit_run, format_audit
from appscreenmap.a11y.report import write_reports
from appscreenmap.reports.health import build_report, format_report
from appscreenmap.reports.perf import format_perf
from appscreenmap.reports.perf import summarize as summarize_perf


def cmd_report(args) -> int:
    rep = build_report(args.run)
    print(json.dumps(rep, indent=1) if args.json else format_report(rep))
    return 0


def cmd_perf(args) -> int:
    rep = summarize_perf(args.run, budget_ms=args.budget)
    print(json.dumps(rep, indent=1) if args.json else format_perf(rep))
    return 0


def cmd_a11y(args) -> int:
    rep = audit_run(args.run)
    print(json.dumps(rep, indent=1) if args.json else format_audit(rep, args.level))
    if args.report:
        out = write_reports(args.run, args.level)
        print(f"\nreport: {out['html']}\n        {out['md']}")
    return 0


def register(sub) -> None:
    s = sub.add_parser("report", help="health report for a run: wasted steps, identity issues, failures")
    s.add_argument("run")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("perf", help="navigation performance: screen load times, jank, cold start")
    s.add_argument("run")
    s.add_argument(
        "--budget", type=int, default=1000, help="load-time budget per screen in ms (default 1000)"
    )
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_perf)

    s = sub.add_parser("a11y", help="WCAG 2.2 checks across a run (writes a11y.json)")
    s.add_argument("run")
    s.add_argument("--level", choices=["A", "AA", "AAA"], default="AA", help="highest level to show")
    s.add_argument("--json", action="store_true")
    s.add_argument("--report", action="store_true", help="also write a11y-report.html and a11y-report.md")
    s.set_defaults(fn=cmd_a11y)
