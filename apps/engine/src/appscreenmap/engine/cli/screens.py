"""`add-screen` / `edit-screen`: file a screen a crawl or recording missed on the app's canvas, then refresh what is
derived from the map (Maestro flows, accessibility findings and reports). The dashboard endpoint calls the same
`file_screen` / `fix_screen`."""

from __future__ import annotations

import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path

from appscreenmap.a11y.checks import audit_run
from appscreenmap.a11y.report import write_reports
from appscreenmap.core import manual
from appscreenmap.core.runs import resolve_run
from appscreenmap.exporters.export import export_run


def refresh(run_dir: Path, reports: bool = True) -> None:
    """Flows and the a11y findings are cheap (~20 ms); the HTML report embeds every screenshot (~1 s on 200 screens),
    so it is rewritten only when what it shows may have changed."""
    export_run(run_dir)
    audit_run(run_dir)
    if reports:
        write_reports(run_dir)


def file_screen(run_dir: Path, image: bytes, title: str, *, refresh_derived: bool = True, **kw) -> dict:
    row = manual.add_screen(run_dir, image, title, **kw)
    if refresh_derived:
        refresh(
            run_dir, reports=bool(kw.get("hierarchy"))
        )  # no hierarchy: no findings, nothing new in the report
    return row


def fix_screen(run_dir: Path, sid: str, *, refresh_derived: bool = True, **kw) -> dict:
    row = manual.update_screen(run_dir, sid, **kw)
    if refresh_derived:
        refresh(run_dir, reports=any(kw.get(k) for k in ("image", "hierarchy", "captures")))
    return row


def parse_multipart(content_type: str, body: bytes) -> dict[str, bytes]:
    """The parts of a multipart/form-data body by field name (stdlib only: `cgi` is gone)."""
    msg = BytesParser(policy=policy.HTTP).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
    )
    if not msg.is_multipart():
        raise manual.ManualError("expected multipart/form-data")
    return {
        p.get_param("name", header="content-disposition"): p.get_payload(decode=True) or b""
        for p in msg.iter_parts()
    }


def _run_dir(args) -> Path | None:
    p = Path(args.canvas)
    d = p if (p / "map.json").is_file() else resolve_run(Path(args.out), args.canvas)
    if d is None:
        print(f"no canvas {args.canvas}", file=sys.stderr)
    return d


def cmd_add(args) -> int:
    d = _run_dir(args)
    if d is None:
        return 2
    try:
        row = file_screen(
            d,
            Path(args.image).read_bytes(),
            args.title,
            parent=args.parent,
            via=args.via,
            scenario=args.scenario,
            new_scenario=args.new_scenario,
            refresh_derived=not args.no_refresh,
            hierarchy=Path(args.hierarchy).read_text(encoding="utf-8") if args.hierarchy else None,
        )
    except (manual.ManualError, OSError) as e:
        print(f"add-screen failed: {e}", file=sys.stderr)
        return 2
    print(
        f"added {row['id']} '{row['title']}' to {d.name}" + (f", under {args.parent}" if args.parent else "")
    )
    return 0


def cmd_edit(args) -> int:
    d = _run_dir(args)
    if d is None:
        return 2
    try:
        row = fix_screen(
            d,
            args.screen,
            title=args.title,
            parent=args.parent,
            via=args.via,
            scenario=args.scenario,
            refresh_derived=not args.no_refresh,
            image=Path(args.image).read_bytes() if args.image else None,
            hierarchy=Path(args.hierarchy).read_text(encoding="utf-8") if args.hierarchy else None,
            captures={n: Path(f).read_bytes() for n, f in (c.split("=", 1) for c in args.capture)},
        )
    except (manual.ManualError, OSError) as e:
        print(f"edit-screen failed: {e}", file=sys.stderr)
        return 2
    print(f"updated {row['id']} '{row['title']}' in {d.name}")
    return 0


def register(sub) -> None:
    a = sub.add_parser("add-screen", help="file a screenshot the crawl missed on the app's canvas, by hand")
    a.add_argument("canvas", help="the app's canvas: run id or folder")
    a.add_argument("--image", required=True, help="screenshot, PNG or JPEG")
    a.add_argument("--title", required=True, help="the screen's name")
    a.add_argument(
        "--hierarchy", help="uiautomator XML of the screen (adds patterns and accessibility checks)"
    )
    a.add_argument(
        "--from", dest="parent", metavar="SCREEN", help="the screen that leads here (adds the link)"
    )
    a.add_argument("--via", help="label of the tap that leads here (default: the title)")
    a.add_argument("--scenario", help="scenario id (default: the parent's, else the last)")
    a.add_argument(
        "--new-scenario", metavar="LABEL", help="start a tree of its own under this scenario name (no --from)"
    )
    a.add_argument(
        "--no-refresh",
        action="store_true",
        help="skip rewriting flows and reports (for a batch: leave it off on the last)",
    )
    a.add_argument("--out", default="runs", help="runs directory (default: ./runs)")
    a.set_defaults(fn=cmd_add)
    e = sub.add_parser("edit-screen", help="fix a manually added screen: title, parent link or scenario")
    e.add_argument("canvas", help="the app's canvas: run id or folder")
    e.add_argument("screen", help="screen id, e.g. s017")
    e.add_argument("--title")
    e.add_argument("--image", help="replace the screenshot (PNG or JPEG)")
    e.add_argument("--hierarchy", help="replace the uiautomator XML")
    e.add_argument(
        "--capture",
        action="append",
        default=[],
        metavar="NAME=FILE",
        help="add an extra shot, e.g. bottom=scrolled.png",
    )
    e.add_argument("--from", dest="parent", metavar="SCREEN", help="move it under another screen")
    e.add_argument("--via", help="relabel the link")
    e.add_argument("--scenario")
    e.add_argument("--no-refresh", action="store_true", help="skip rewriting flows and reports (for a batch)")
    e.add_argument("--out", default="runs", help="runs directory (default: ./runs)")
    e.set_defaults(fn=cmd_edit)
