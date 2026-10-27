"""`stack`: what an app installed on the emulator (or iOS simulator) is built with, written to its canvas as
audits/stack.json."""

from __future__ import annotations

import json
import shutil
import subprocess
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
from appscreenmap.drivers.ios import IosSimulatorDriver, app_container
from appscreenmap.stack import (
    BUILD_DIR,
    build_audit,
    build_ios_audit,
    fingerprint,
    fingerprint_app,
    parse_dumpsys_package,
    write_audit,
)


def find_canvas(runs_root: Path, package: str, platform: str = "android") -> tuple[Path | None, list[Path]]:
    """The app's one canvas on `platform`: (it, []) when there is one, (None, candidates) when there are none or
    several. Android and iOS builds of one app have separate canvases."""
    runs = []
    for d in iter_run_dirs(runs_root):
        try:
            run = json.loads((d / "map.json").read_text()).get("run", {})
        except (OSError, ValueError):
            continue
        on = "ios" if run.get("device", {}).get("platform") == "ios" else "android"
        if run.get("app", {}).get("package") == package and on == platform:
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


def _resolve_canvas(args, runs_root: Path, platform: str) -> tuple[Path | None, int]:
    """(canvas or None to create one, 0), or (None, exit code) when the canvas given or found is wrong."""
    canvas = Path(args.run) if args.run else None
    name = "iOS" if platform == "ios" else "Android"
    if canvas and not (canvas / "map.json").is_file():
        print(f"Not a run directory (no map.json): {canvas}", file=sys.stderr)
        return None, 2
    if canvas:
        run = json.loads((canvas / "map.json").read_text())["run"]
        on = "ios" if run.get("device", {}).get("platform") == "ios" else "android"
        if run.get("app", {}).get("package") != args.package or on != platform:
            print(f"{canvas} is not the {name} canvas of {args.package}.", file=sys.stderr)
            return None, 2
        return canvas, 0
    canvas, candidates = find_canvas(runs_root, args.package, platform)  # before reading the app: fail fast
    if candidates:
        print(
            f"{args.package} has several {name} runs; pass its canvas: appscreenmap stack <canvas> --package …\n  "
            + "\n  ".join(str(c) for c in candidates),
            file=sys.stderr,
        )
        return None, 2
    return canvas, 0


def _simulator(serial: str | None) -> tuple[str, str] | None:
    """(udid, "iPhone 17 · iOS 27.0") of the booted simulator to read: `serial` or the only one booted."""
    try:
        booted = IosSimulatorDriver.list_devices()
    except (OSError, subprocess.SubprocessError):  # no Xcode tools
        return None
    if serial:
        return next((b for b in booted if b[0] == serial), None)
    return booted[0] if len(booted) == 1 else None


def new_ios_canvas(runs_root: Path, udid: str, name: str, package: str, fp: dict) -> Path:
    """An empty iOS canvas, in the `<project>-ios` folder like iOS crawls. Device facts come from the driver when
    idb is there, else from simctl's device list alone."""
    try:
        device = IosSimulatorDriver(udid).info()
    except (DriverError, OSError, ValueError, subprocess.TimeoutExpired):
        model, _, release = name.partition(" · ")
        device = {
            "serial": udid,
            "platform": "ios",
            "type": "emulator",
            "name": f"{model} (Simulator)",
            "model": model,
            "manufacturer": "Apple",
            "os": {"name": "iOS", "release": release.removeprefix("iOS ")},
        }
    app = {
        "package": package,
        "version": fp.get("version"),
        "build": fp.get("build"),
        "label": fp.get("label") or package.rsplit(".", 1)[-1],
        "min_os": fp.get("deployment_target"),
        "platform": "ios",
        "activities": [],
        "launch_activity": None,
    }
    run_dir = new_run_dir(runs_root, package, project=f"{package.rsplit('.', 1)[-1]}-ios")
    now = datetime.now(UTC).isoformat(timespec="seconds")
    run = {
        "id": run_dir.name,
        "status": "done",
        "source": "scan",
        "started_at": now,
        "finished_at": now,
        "tool": f"appscreenmap {__version__}",
        "app": app,
        "device": device,
        "steps": 0,
        "elapsed_s": 0,
    }
    AppMap(run).save(run_dir / "map.json")
    return run_dir


def keep_app(canvas: Path, app: Path) -> Path:
    """The scanned `.app` stays with the canvas (`build/app/`), like the APKs on Android. Only the latest is kept."""
    build = canvas / BUILD_DIR
    shutil.rmtree(build, ignore_errors=True)
    (build / "app").mkdir(parents=True)
    shutil.copytree(app, build / "app" / app.name, symlinks=True)
    return build


def _cmd_stack_ios(args, runs_root: Path) -> int:
    canvas, code = _resolve_canvas(args, runs_root, "ios")
    if code:
        return code
    sim = _simulator(args.serial)
    if sim is None:
        print(
            "No booted iOS simulator"
            + (f" with udid {args.serial}." if args.serial else " (or several: pass --serial <udid>).")
            + " Boot one: `xcrun simctl boot <name>`.",
            file=sys.stderr,
        )
        return 2
    udid, name = sim
    app = app_container(udid, args.package, "app")
    if app is None or not app.is_dir():
        print(f"{args.package} is not installed on {name}. Install it first.", file=sys.stderr)
        return 2
    data = app_container(udid, args.package, "data")
    fp = fingerprint_app(app)
    if canvas is None:
        canvas = new_ios_canvas(runs_root, udid, name, args.package, fp)
        print(
            f"new canvas for {args.package}: {canvas} (a crawl merges into it later)",
            file=sys.stderr if args.json else sys.stdout,
        )
    keep_app(canvas, app)
    activity.bind_run(canvas)
    audit = build_ios_audit(fp, f"appscreenmap {__version__} (simulator read)", str(data) if data else None)
    return _report(audit, write_audit(canvas, audit), runs_root, args.json)


def _report(audit: dict, path: Path, runs_root: Path, as_json: bool) -> int:
    update_index(runs_root)
    if as_json:
        print(json.dumps(audit, indent=1, ensure_ascii=False))
        return 0
    facts = audit["facts"]
    print(f"stack: {audit['summary']}")
    for m in audit["metrics"]:
        print(f"  {m['label']:17} {m['value']}" + (f"  ({m['hint']})" if m.get("hint") else ""))
    for s in facts["signals"]:
        print(f"  {s['confidence']:8} {s['label']:32} {', '.join(s['evidence'][:3])}")
    for st in facts["storage"]:
        enc = {True: "encrypted", False: "plain", None: "encryption optional"}[st["encrypted"]]
        print(f"  storage  {st['label']:32} {enc}; {', '.join(st['locations']) or 'no file'}")
    if facts.get("platform") == "ios":  # the binary's own build version, to compare with Info.plist above
        print(f"  binary            min OS {facts.get('min_os')} · SDK {facts.get('sdk')} (LC_BUILD_VERSION)")
    for f in audit["findings"]:
        print(f"  {f['severity']:8} {f['title']}")
    for n in facts["notes"]:
        print(f"  ! {n}")
    print(f"report: {path}  (Insights in `appscreenmap serve`)")
    return 0


def cmd_stack(args) -> int:
    runs_root = Path(args.out)
    if getattr(args, "platform", "android") == "ios":
        return _cmd_stack_ios(args, runs_root)
    canvas, code = _resolve_canvas(args, runs_root, "android")
    if code:
        return code
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
    return _report(audit, write_audit(canvas, audit), runs_root, args.json)


def register(sub) -> None:
    s = sub.add_parser(
        "stack",
        help="what an app on the emulator or iOS simulator is built with (framework, SDK levels, libraries, storage) "
        "→ audits/stack.json",
    )
    s.add_argument("run", nargs="?", help="the app's canvas (default: found by package, or created empty)")
    s.add_argument("--package", required=True, help="the installed app's package name (bundle id on iOS)")
    s.add_argument(
        "--platform",
        choices=["android", "ios"],
        default="android",
        help="android (default) or ios (simulator)",
    )
    s.add_argument("--serial", help="device serial or simulator udid (default: the only one)")
    s.add_argument("--out", default="runs", help="runs directory (default: ./runs)")
    s.add_argument("--json", action="store_true", help="print the audit as JSON")
    s.set_defaults(fn=cmd_stack)
