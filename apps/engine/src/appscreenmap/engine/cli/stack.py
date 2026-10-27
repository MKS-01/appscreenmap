"""`stack`: what an app installed on the emulator is built with, written to its canvas as audits/stack.json."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from appscreenmap.core import __version__, activity
from appscreenmap.core.model import AppMap
from appscreenmap.core.runs import iter_run_dirs, new_run_dir, update_index
from appscreenmap.drivers.android import AdbDriver
from appscreenmap.drivers.apkinfo import apk_info
from appscreenmap.drivers.base import DriverError
from appscreenmap.stack import BUILD_DIR, build_audit, fingerprint, parse_dumpsys_package, write_audit


def find_canvas(runs_root: Path, package: str) -> tuple[Path | None, list[Path]]:
    """The app's one Android canvas: (it, []) when there is one, (None, candidates) when there are none or several."""
    runs = []
    for d in iter_run_dirs(runs_root):
        try:
            run = json.loads((d / "map.json").read_text()).get("run", {})
        except (OSError, ValueError):
            continue
        if run.get("app", {}).get("package") == package and run.get("device", {}).get("platform") != "ios":
            runs.append((d, bool(run.get("scenarios"))))
    if len(runs) == 1:
        return runs[0][0], []
    canvases = [d for d, merged in runs if merged]
    if len(canvases) == 1:
        return canvases[0], []
    return None, sorted(d for d, _ in runs)


def new_canvas(runs_root: Path, d: AdbDriver, package: str, base: Path) -> Path:
    """An empty canvas (zero screens) for an app scanned before its first crawl; a crawl merges into it later."""
    app = apk_info(base)
    app.setdefault("package", package)
    app.setdefault("version", d.app_version(package))
    app.setdefault("label", package.rsplit(".", 1)[-1])
    app.setdefault("activities", [])
    app.setdefault("launch_activity", d.resolve_launch_activity(package))
    run_dir = new_run_dir(runs_root, package)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    run = {
        "id": run_dir.name,
        "status": "done",
        "source": "scan",  # made by a scan, not a crawl: a merge adds no scenario for it
        "started_at": now,
        "finished_at": now,
        "tool": f"appscreenmap {__version__}",
        "app": app,
        "device": d.info(),
        "steps": 0,
        "elapsed_s": 0,
    }
    AppMap(run).save(run_dir / "map.json")
    return run_dir


def keep_build(canvas: Path, apks: list[Path], dumpsys: str) -> Path:
    """The scanned build stays with the canvas (`build/`): the security scan and the Frida probe read the same APKs
    and package dump instead of pulling again. Only the latest scanned build is kept."""
    build = canvas / BUILD_DIR
    shutil.rmtree(build, ignore_errors=True)
    (build / "apks").mkdir(parents=True)
    for apk in apks:
        shutil.move(apk, build / "apks" / apk.name)
    (build / "dumpsys-package.txt").write_text(dumpsys)
    return build


def cmd_stack(args) -> int:
    runs_root = Path(args.out)
    canvas = Path(args.run) if args.run else None
    if canvas and not (canvas / "map.json").is_file():
        print(f"Not a run directory (no map.json): {canvas}", file=sys.stderr)
        return 2
    if canvas:
        run = json.loads((canvas / "map.json").read_text())["run"]
        on = run.get("app", {}).get("package")
        if on != args.package or run.get("device", {}).get("platform") == "ios":
            print(f"{canvas} is not the Android canvas of {args.package}.", file=sys.stderr)
            return 2
    else:  # before pulling anything: an ambiguous canvas fails fast
        canvas, candidates = find_canvas(runs_root, args.package)
        if candidates:
            print(
                f"{args.package} has several runs; pass its canvas: appscreenmap stack <canvas> --package …\n  "
                + "\n  ".join(str(c) for c in candidates),
                file=sys.stderr,
            )
            return 2
    d = AdbDriver(args.serial)
    if not d.is_installed(args.package):
        print(f"{args.package} is not installed on {d.serial}. Install it first.", file=sys.stderr)
        return 2
    dumpsys = d.dumpsys_package(args.package)
    device = parse_dumpsys_package(dumpsys, args.package)
    with tempfile.TemporaryDirectory(prefix="asm-stack-") as tmp:
        apks = []
        for remote in d.apk_paths(args.package):
            local = Path(tmp) / Path(remote).name
            try:
                d.pull(remote, local)
                apks.append(local)
            except DriverError as e:
                print(f"could not pull {remote}: {e}", file=sys.stderr)
        if not apks:
            print(f"Could not pull any APK of {args.package} from {d.serial}.", file=sys.stderr)
            return 2
        fp = fingerprint(apks)
        if canvas is None:
            canvas = new_canvas(runs_root, d, args.package, apks[0])
            print(
                f"new canvas for {args.package}: {canvas} (a crawl merges into it later)",
                file=sys.stderr if args.json else sys.stdout,  # --json keeps stdout to the audit alone
            )
        keep_build(canvas, apks, dumpsys)
    activity.bind_run(canvas)
    audit = build_audit(args.package, device, fp, f"appscreenmap {__version__} (device read)")
    path = write_audit(canvas, audit)
    update_index(runs_root)
    if args.json:
        print(json.dumps(audit, indent=1, ensure_ascii=False))
        return 0
    facts = audit["facts"]
    print(f"stack: {audit['summary']}")
    for m in audit["metrics"]:
        print(f"  {m['label']:15} {m['value']}" + (f"  ({m['hint']})" if m.get("hint") else ""))
    for s in facts["signals"]:
        print(f"  {s['confidence']:8} {s['label']:32} {', '.join(s['evidence'][:3])}")
    for st in facts["storage"]:
        enc = {True: "encrypted", False: "plain", None: "encryption optional"}[st["encrypted"]]
        print(f"  storage  {st['label']:32} {enc}; {', '.join(st['locations']) or 'no file'}")
    for f in audit["findings"]:
        print(f"  {f['severity']:8} {f['title']}")
    for n in facts["notes"]:
        print(f"  ! {n}")
    print(f"report: {path}  (Insights in `appscreenmap serve`)")
    return 0


def register(sub) -> None:
    s = sub.add_parser(
        "stack",
        help="what an app on the emulator is built with (framework, SDK levels, ABIs, libraries) → audits/stack.json",
    )
    s.add_argument("run", nargs="?", help="the app's canvas (default: found by package, or created empty)")
    s.add_argument("--package", required=True, help="the installed app's package name")
    s.add_argument("--serial", help="device serial (default: the only device)")
    s.add_argument("--out", default="runs", help="runs directory (default: ./runs)")
    s.add_argument("--json", action="store_true", help="print the audit as JSON")
    s.set_defaults(fn=cmd_stack)
