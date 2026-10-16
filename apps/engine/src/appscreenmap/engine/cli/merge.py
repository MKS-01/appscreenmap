"""`merge`: several runs of one app on one canvas, one scenario per run."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from appscreenmap.a11y.checks import audit_run
from appscreenmap.a11y.report import write_reports
from appscreenmap.core.merge import merge_runs
from appscreenmap.core.runs import project_for, slug, update_index
from appscreenmap.exporters.export import export_run
from appscreenmap.reports.perf import summarize as summarize_perf


def cmd_merge(args) -> int:
    runs = [Path(r) for r in args.runs]
    canvas = Path(args.into) if args.into else None
    for r in [*runs, *([canvas] if canvas else [])]:
        if not (r / "map.json").is_file():
            print(f"not a run folder: {r}", file=sys.stderr)
            return 2
    labels = args.labels.split(",") if args.labels else None
    runs_root = Path(args.out)
    sources = [canvas, *runs] if canvas else runs
    if canvas and labels:
        labels = ["", *labels]
    package = json.loads((sources[0] / "map.json").read_text())["run"]["app"]["package"]
    if canvas:
        # Added in place: the canvas keeps its id and folder; the merge is built beside it, then swapped in.
        name, out_dir = canvas.name, canvas.parent / f".merge-{canvas.name}"
        shutil.rmtree(out_dir, ignore_errors=True)
    else:
        proj = project_for(
            package, args.project or (runs[0].parent.name if runs[0].parent != runs_root else None)
        )
        name = f"{slug(args.name)}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        out_dir = runs_root / proj / name
    out_dir.mkdir(parents=True, exist_ok=False)
    try:
        data = merge_runs(sources, out_dir, name, labels)
    except ValueError as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        print(f"merge failed: {e}", file=sys.stderr)
        return 2
    export_run(out_dir)
    audit = audit_run(out_dir)
    write_reports(out_dir)
    summarize_perf(out_dir)
    if canvas:
        shutil.rmtree(canvas)
        out_dir.rename(canvas)
        out_dir = canvas
    if args.move:  # the runs now live in the canvas: drop their own folders so the app keeps one canvas
        for r in runs:
            if r.resolve() != out_dir.resolve():
                shutil.rmtree(r)
    update_index(runs_root)
    st = data["stats"]
    verb = "added to" if canvas else "merged into"
    print(f"{len(runs)} run(s) {verb} {out_dir}: {st['screens']} screens, {st['transitions']} transitions")
    for sc in data["run"]["scenarios"]:
        print(
            f"  {sc['id']} {sc['label']}: {len(sc['screens'])} screens, entry {', '.join(sc['entry']) or '-'}"
        )
    print(f"  {audit['summary']['issues']} WCAG 2.2 findings")
    return 0


def register(sub) -> None:
    s = sub.add_parser("merge", help="put several runs of one app on one canvas, one scenario per run")
    s.add_argument(
        "runs", nargs="+", help="run folders, in the order of the scenarios (with --into: the runs to add)"
    )
    s.add_argument("--name", default="merged", help="name prefix of the merged run (default: merged)")
    s.add_argument(
        "--move",
        action="store_true",
        help="delete the merged runs' own folders once they are in the canvas (one canvas per app)",
    )
    s.add_argument("--labels", help="comma-separated scenario names, one per run (default: the run names)")
    s.add_argument(
        "--into", help="an existing canvas (merged run) to add the runs to, in place: same id and folder"
    )
    s.add_argument("--project", help="project folder under runs/ (default: the first run's)")
    s.add_argument("--out", default="runs", help="runs directory (default: ./runs)")
    s.set_defaults(fn=cmd_merge)
