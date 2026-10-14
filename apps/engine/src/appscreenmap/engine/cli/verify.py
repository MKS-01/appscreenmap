"""Compare builds and generate tests: `export`, `diff`, `verify`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from appscreenmap.a11y.checks import audit_run
from appscreenmap.a11y.report import write_reports
from appscreenmap.core.model import load_map
from appscreenmap.core.runs import update_index
from appscreenmap.drivers.android import AdbDriver
from appscreenmap.exporters.export import export_run
from appscreenmap.regression.verify import format_verify, required_secrets, update_baselines, verify_run
from appscreenmap.regression.visual import diff_runs


def cmd_export(args) -> int:
    res = export_run(args.run)
    print(f"✔ {res['flows']} Maestro flows, Mermaid → {res['mermaid']}")
    return 0


def cmd_diff(args) -> int:
    rep = diff_runs(args.base, args.cand, threshold=args.threshold)
    s = rep["summary"]
    print(f"✔ {s['changed']} changed, {s['new']} new, {s['missing']} missing, {s['same']} unchanged")
    for i in rep["items"]:
        if i["status"] != "same":
            extra = f"{i['changed_ratio']:.2%} pixels" if i.get("changed_ratio") is not None else ""
            if t := i.get("text"):
                counts = ", ".join(f"{t[k]} {k}" for k in ("added", "removed", "moved", "changed") if t[k])
                extra += f"; text {counts}" if counts else ""
            print(
                f"  {i['status']:8} {i.get('base') or '-':>5} → {i.get('cand') or '-':<5} {i.get('title')!r} {extra}"
            )
    update_index(Path(args.runs))
    return 0


def cmd_verify(args) -> int:
    base = Path(args.base)
    if not (base / "map.json").is_file():
        print(f"Not a run directory (no map.json): {base}", file=sys.stderr)
        return 2
    data = load_map(base)
    if missing := [n for n in required_secrets(data) if n not in os.environ]:
        print(
            f"Set {', '.join(missing)}: the recorded form inputs use them as ${{NAME}} placeholders.",
            file=sys.stderr,
        )
        return 2
    d = AdbDriver(args.serial)
    pkg = data["run"]["app"]["package"]
    if args.apk:
        print(f"📦 installing {Path(args.apk).name} …")
        d.install(args.apk, grant=data["run"].get("config", {}).get("grant_permissions", True))
    elif not d.is_installed(pkg):
        print(
            f"{pkg} is not installed on {d.serial}. Pass --apk to install the build to verify.",
            file=sys.stderr,
        )
        return 2
    print(f"🔁 verifying {pkg} {d.app_version(pkg) or ''} against {data['run']['id']} on {d.serial}")
    rep = verify_run(
        base,
        d,
        clear_data=args.clear_data,
        only=args.screen or None,
        threshold=args.threshold,
        out_dir=args.out,
    )
    print(
        json.dumps({k: v for k, v in rep.items() if not k.startswith("_")}, indent=1)
        if args.json
        else format_verify(rep)
    )
    if args.update_baselines and rep["status"] == "done":
        updated = update_baselines(base, rep)
        audit_run(base)
        write_reports(base)
        print(f"📌 baselines updated for {len(updated)} screen(s): {', '.join(updated)}")
    update_index(Path(args.runs))
    if rep["status"] != "done":
        return 1
    if not rep["ok"] or (args.fail_on_change and rep["summary"]["changed"]):
        return 1
    return 0


def register(sub) -> None:
    s = sub.add_parser("export", help="regenerate Maestro flows and Mermaid for a run")
    s.add_argument("run")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("diff", help="visual diff of two runs (e.g. two builds)")
    s.add_argument("base", help="baseline run directory")
    s.add_argument("cand", help="candidate run directory")
    s.add_argument("--threshold", type=float, default=0.6, help="screen match similarity (0–1)")
    s.add_argument("--runs", default="runs", help="runs directory to re-index (default: ./runs)")
    s.set_defaults(fn=cmd_diff)

    s = sub.add_parser(
        "verify", help="replay every screen's path on a new build (CI: exit 1 on broken paths)"
    )
    s.add_argument("base", help="baseline run directory (its paths are replayed)")
    s.add_argument("--apk", help="install this build first (default: the installed app)")
    s.add_argument("--serial", help="device serial (default: the only connected device)")
    s.add_argument(
        "--clear-data",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="wipe app data before each path (default: as the base run was crawled)",
    )
    s.add_argument("--screen", action="append", help="only these screens (repeatable)")
    s.add_argument("--threshold", type=float, default=0.6, help="screen match similarity (0–1)")
    s.add_argument("--fail-on-change", action="store_true", help="also exit 1 when a screen looks different")
    s.add_argument(
        "--update-baselines",
        action="store_true",
        help="accept the new look: copy passed screens' screenshots and hierarchies into the base run",
    )
    s.add_argument("--out", help="output directory (default: <base>/verify/<verify-id>)")
    s.add_argument("--runs", default="runs", help="runs directory to re-index (default: ./runs)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_verify)
