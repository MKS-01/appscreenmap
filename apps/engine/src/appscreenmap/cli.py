"""Command line entry point: doctor, crawl, export, diff, verify, mcp, serve."""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import shutil
import signal
import sys
import tempfile
import webbrowser
from datetime import UTC, datetime
from pathlib import Path

from appscreenmap.core import __version__, notes
from appscreenmap.core.config import CrawlConfig
from appscreenmap.core.model import AppMap, load_map
from appscreenmap.core.runs import new_run_dir, resolve_run, update_index
from appscreenmap.drivers.android import AdbDriver
from appscreenmap.drivers.apkinfo import apk_info, find_aapt2
from appscreenmap.drivers.base import DriverError
from appscreenmap.drivers.device import describe

from .a11y import audit_run, format_audit
from .a11y_report import write_reports
from .explorer import CrawlAborted, Explorer
from .export import export_run
from .perf import format_perf
from .perf import summarize as summarize_perf
from .report import build_report, format_report
from .security import (
    load_evidence,
    parse_frida_log,
    scan_apk,
    scan_device_data,
    write_audit,
)
from .verify import format_verify, required_secrets, update_baselines, verify_run
from .visual import diff_runs


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _doctor_ios(row) -> None:
    """iOS Simulator tooling. Optional: nothing here fails `doctor` unless an iOS simulator is booted without idb."""
    if sys.platform != "darwin":
        return
    xcrun = shutil.which("xcrun")
    if not xcrun:
        print("  · iOS: Xcode not installed (optional: only needed to crawl iOS apps)")
        return
    from appscreenmap.drivers.ios import IosSimulatorDriver

    sims = IosSimulatorDriver.list_devices()
    idb = bool(shutil.which("idb") or shutil.which("uvx"))
    companion = bool(shutil.which("idb_companion"))
    row(
        True,
        "iOS simulators booted",
        ", ".join(f"{u[:8]} {n}" for u, n in sims) or "none (boot one in Device Hub)",
    )
    if sims or idb or companion:
        row(
            idb,
            "idb client (iOS taps and accessibility tree)",
            "found" if idb else "`uv tool install fb-idb`",
        )
        row(companion, "idb_companion", "found" if companion else "`brew install facebook/fb/idb-companion`")


def cmd_doctor(args) -> int:
    ok = True

    def row(good: bool, label: str, detail: str = "") -> None:
        nonlocal ok
        ok &= good
        print(f"  {'✔' if good else '✘'} {label}{'  — ' + detail if detail else ''}")

    print(f"AppScreenMap {__version__}")
    adb = shutil.which("adb")
    row(bool(adb), "adb", adb or "install Android platform-tools")
    devices = AdbDriver.list_devices()
    ready = [s for s, st in devices if st == "device"]
    row(bool(ready), "device", ", ".join(f"{s} ({st})" for s, st in devices) or "none connected")
    for serial in ready:
        d = AdbDriver(serial)
        info = d.info()
        row(True, f"{serial}", f"{describe(info)}, {info['width']}x{info['height']}")
    _doctor_ios(row)
    aapt2 = find_aapt2()
    row(bool(aapt2), "aapt2 (optional: activity coverage)", aapt2 or "not found in Android SDK build-tools")
    dist = _web_dist()
    row(
        dist is not None,
        "web viewer build (for `serve`)",
        str(dist) if dist else "run `bun install && bun run build` in web/",
    )
    return 0 if ok else 1


def _setup_android(args, cfg: CrawlConfig):
    """Connect, install if asked, and describe the app. Returns (driver, app, package, launch_activity) or an exit code."""
    d = AdbDriver(args.serial)
    app: dict = {}
    if args.apk:
        apk = Path(args.apk)
        if not apk.is_file():
            print(f"APK not found: {apk}", file=sys.stderr)
            return 2
        app = apk_info(apk)
        package = args.package or app.get("package")
        if not package:
            print(
                "Could not read the package name from the APK (aapt2 missing?). Pass --package.",
                file=sys.stderr,
            )
            return 2
        print(f"📦 installing {apk.name} ({package}) …")
        d.install(apk, grant=cfg.grant_permissions)
    else:
        package = args.package
        if not d.is_installed(package):
            print(f"{package} is not installed on {d.serial}. Pass --apk to install it.", file=sys.stderr)
            return 2
        remote = d.apk_path(package)
        if remote and find_aapt2():
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    d.pull(remote, Path(tmp) / "base.apk")
                    app = apk_info(Path(tmp) / "base.apk")
                except DriverError:
                    app = {}
    app.setdefault("package", package)
    app.setdefault("version", d.app_version(package))
    app.setdefault("label", package.rsplit(".", 1)[-1])
    app.setdefault("activities", [])
    launch = args.activity or app.get("launch_activity") or d.resolve_launch_activity(package)
    app["launch_activity"] = launch

    return d, app, package, launch


def _setup_ios(args, cfg: CrawlConfig):
    """Same for an iOS Simulator: install a `.app` if given, read its Info.plist. Returns (driver, app, bundle_id, None)."""
    import plistlib

    from appscreenmap.drivers.ios import IosSimulatorDriver

    d = IosSimulatorDriver(args.serial)
    app: dict = {}
    if args.app:
        bundle = Path(args.app)
        plist = bundle / "Info.plist"
        if not plist.is_file():
            print(
                f"Not an app bundle (no Info.plist): {bundle}. Pass the .app from an iphonesimulator build.",
                file=sys.stderr,
            )
            return 2
        info = plistlib.loads(plist.read_bytes())
        package = args.package or info.get("CFBundleIdentifier")
        app = {
            "package": package,
            "version": info.get("CFBundleShortVersionString"),
            "build": info.get("CFBundleVersion"),
            "label": info.get("CFBundleDisplayName") or info.get("CFBundleName"),
            "min_os": info.get("MinimumOSVersion"),
        }
        print(f"📦 installing {bundle.name} ({package}) …")
        d.install(bundle)
    else:
        package = args.package
        if not d.is_installed(package):
            print(f"{package} is not installed on {d.udid}. Pass --app to install it.", file=sys.stderr)
            return 2
        app = {"version": d.app_version(package)}
    app.setdefault("package", package)
    app.setdefault("label", package.rsplit(".", 1)[-1])
    app["platform"] = "ios"
    app["activities"] = []
    app["launch_activity"] = None
    return d, app, package, None


def cmd_crawl(args) -> int:
    cfg = CrawlConfig.load(
        args.config,
        max_steps=args.max_steps,
        max_minutes=args.max_minutes,
        clear_data=True if args.clear_data else None,
        settle_seconds=args.settle,
        font_scale=args.font_scale,
        disable_animations=False if args.keep_animations else None,
    )
    if missing := cfg.missing_secrets():
        print(
            f"Set {', '.join(missing)} in the environment: [inputs] uses them as ${{NAME}} placeholders.",
            file=sys.stderr,
        )
        return 2
    ios = bool(args.app) or args.platform == "ios"
    if ios:
        cfg.measure_load = (
            False  # load timing reads Android's frame counters; iOS has no equivalent wired yet
        )
    setup = (_setup_ios if ios else _setup_android)(args, cfg)
    if isinstance(setup, int):
        return setup
    d, app, package, launch = setup

    original_font_scale = None
    if cfg.font_scale:
        original_font_scale = d.get_font_scale()
        d.set_font_scale(cfg.font_scale)

    runs_root = Path(args.out)
    # Android and iOS builds of one app have different screens: keep their runs in separate project folders.
    project = args.project or (f"{package.rsplit('.', 1)[-1]}-ios" if ios else None)
    run_dir = new_run_dir(runs_root, package, args.name, project)
    run = {
        "id": run_dir.name,
        "status": "running",
        "started_at": _now(),
        "finished_at": None,
        "tool": f"appscreenmap {__version__}",
        "app": app,
        "device": d.info(),
        "config": cfg.to_dict(),
    }
    amap = AppMap(run)
    amap.save(run_dir / "map.json")
    update_index(runs_root)
    print(
        f"🗺  mapping {app.get('label')} {app.get('version') or ''} on {run['device']['name']} ({run['device']['type']}) → {run_dir}"
    )
    print(
        f"   budget: {cfg.max_steps} steps / {cfg.max_minutes:g} min   "
        f"(live view: appscreenmap serve --runs {runs_root})"
    )

    anim = None
    if cfg.disable_animations:
        anim = d.get_animations()
        d.set_animations(0)
    if cfg.clear_data:
        d.clear_data(package)
    if cfg.grant_permissions:
        d.grant_all(package)
    d.clear_crash_log()

    explorer = Explorer(d, package, launch, cfg, run_dir, amap)
    code = 0

    def _terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _terminate)
    signal.signal(signal.SIGHUP, _terminate)
    try:
        explorer.run()
        run["status"] = "done"
    except KeyboardInterrupt:
        run["status"] = "stopped"
        explorer.stop_reason = "stopped by user"
        print("\n⏸ stopped — saving what we have")
    except CrawlAborted as e:
        run["status"] = "failed"
        run["error"] = str(e)
        print(f"✘ {e}", file=sys.stderr)
        code = 1
    except DriverError as e:
        run["status"] = "failed"
        run["error"] = str(e)
        print(f"✘ device error: {e}", file=sys.stderr)
        code = 1
    finally:
        if cfg.stay_in_app:
            try:
                d.unpin()
            except DriverError:
                pass
        if anim is not None:
            try:
                d.set_animations(anim)
            except DriverError:
                pass
        if original_font_scale is not None:
            try:
                d.set_font_scale(original_font_scale)
            except DriverError:
                pass
        run["finished_at"] = _now()
        explorer.save()
        export = export_run(run_dir)
        audit = audit_run(run_dir)
        write_reports(run_dir)
        perf = summarize_perf(run_dir, budget_ms=cfg.perf_budget_ms)
        update_index(runs_root)
    st = amap.stats()
    print(
        f"\n✔ {st['screens']} screens, {st['transitions']} transitions, {st['crashes']} crashes, "
        f"{run['steps']} steps in {run['elapsed_s']:.0f}s"
    )
    if st["activity_coverage"] is not None:
        print(f"  activity coverage: {st['activity_coverage']:.0%} of {st['activities_declared']} declared")
    print(f"  {export['flows']} Maestro flows → {run_dir / 'flows'}")
    if perf["screens"]:
        slowest = perf["screens"][0]
        print(
            f"  slowest screen: {slowest['screen']} '{slowest['title']}' {slowest['median_ms']} ms "
            f"(median); {len(perf['findings'])} perf finding(s) → appscreenmap perf {run_dir}"
        )
    print(f"  {audit['summary']['issues']} WCAG 2.2 findings → {run_dir / 'a11y-report.html'}")
    print(f"  view it: appscreenmap serve --runs {runs_root}")
    return code


def cmd_perf(args) -> int:
    rep = summarize_perf(args.run, budget_ms=args.budget)
    print(json.dumps(rep, indent=1) if args.json else format_perf(rep))
    return 0


def cmd_a11y(args) -> int:
    rep = audit_run(args.run)
    print(json.dumps(rep, indent=1) if args.json else format_audit(rep, args.level))
    if args.report:
        out = write_reports(args.run, args.level)
        print(f"\n📄 report → {out['html']}\n            {out['md']}")
    return 0


def cmd_security(args) -> int:
    run = Path(args.run)
    if not (run / "map.json").is_file():
        print(f"Not a run directory (no map.json): {run}", file=sys.stderr)
        return 2
    data = load_map(run)
    app = data["run"]["app"]
    if (app.get("platform") or data["run"]["device"].get("platform")) == "ios":
        print(
            "The security scanner covers Android builds for now (iOS: see the security-audit skill).",
            file=sys.stderr,
        )
        return 2
    if not (args.apk or args.pull or args.device or args.frida_log):
        print("Nothing to scan: pass --apk FILE, --pull, --device and/or --frida-log FILE.", file=sys.stderr)
        return 2
    sources = load_evidence(run)
    drv = None
    if args.pull or args.device:
        drv = AdbDriver(args.serial)
    apk = args.apk
    if args.pull and not apk:
        remote = drv.apk_path(app["package"])
        if not remote:
            print(f"{app['package']} is not installed on {drv.serial}.", file=sys.stderr)
            return 2
        apk = str(Path(tempfile.mkdtemp(prefix="asm-sec-")) / "base.apk")
        drv.pull(remote, apk)
    if apk:
        sources["apk"] = {**scan_apk(apk), "at": datetime.now(UTC).isoformat(timespec="seconds")}
    if args.device:
        sources["device"] = {
            **scan_device_data(drv, app["package"]),
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
    if args.frida_log:
        sources["frida"] = {
            **parse_frida_log(Path(args.frida_log).read_text(errors="replace")),
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
    audit = write_audit(run, sources)
    if args.json:
        print(json.dumps(audit, indent=1))
        return 0
    print(
        f"🔒 security audit for {app.get('label') or app['package']}: score {audit['score']}, {audit['summary']}"
    )
    for f in audit["findings"]:
        print(f"  {f['severity']:7} {f['title']}")
    for m in audit["metrics"]:
        if m["label"] == "note":
            print(f"  ! {m['value']}")
    print(
        f"📄 {run / 'audits' / 'security.json'}  (open the Insights → Security page in `appscreenmap serve`)"
    )
    return 0


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


def cmd_mcp(args) -> int:
    try:
        from .mcp_server import MapTools, build_server

        server = build_server(MapTools(args.runs, args.run, args.serial))
    except ImportError:
        print("The MCP server needs the mcp extra: pip install 'appscreenmap[mcp]'", file=sys.stderr)
        return 2
    server.run("stdio")
    return 0


def cmd_report(args) -> int:
    rep = build_report(args.run)
    print(json.dumps(rep, indent=1) if args.json else format_report(rep))
    return 0


def _web_dist() -> Path | None:
    candidates = [
        os.environ.get("APPSCREENMAP_WEB"),
        Path(__file__).parent / "web",  # bundled in the wheel
    ]
    candidates += [d / "web" / "dist" for d in Path(__file__).resolve().parents]  # source checkout
    for c in candidates:
        if c and (Path(c) / "index.html").is_file():
            return Path(c)
    return None


class _Handler(http.server.SimpleHTTPRequestHandler):
    runs_root: Path
    web_root: Path

    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith("/runs/"):
            rel = clean[len("/runs/") :]
            # /runs/<run-id>/… → runs/<project>/<run-id>/… (ids are flat; folders are per project)
            head, _, rest = rel.partition("/")
            if (
                head
                and not (self.runs_root / head).exists()
                and (run_dir := resolve_run(self.runs_root, head))
            ):
                rel = run_dir.relative_to(self.runs_root).as_posix() + ("/" + rest if rest else "")
            target = (self.runs_root / rel).resolve()
            if self.runs_root.resolve() not in target.parents and target != self.runs_root.resolve():
                return str(self.runs_root / "__forbidden__")
            return str(target)
        target = (self.web_root / clean.lstrip("/")).resolve()
        if not target.exists() or clean == "/":
            return str(self.web_root / "index.html")  # SPA fallback
        return str(target)

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/runs/index.json":
            update_index(self.runs_root)
        super().do_GET()

    def do_PUT(self):
        """Save viewer notes: PUT /runs/[<project>/]<run-id>/notes.json. The only write the server accepts."""
        parts = self.path.split("?", 1)[0].split("/")
        run_dir = None
        if parts[:2] == ["", "runs"] and parts[-1] == notes.NOTES_FILE and len(parts) in (4, 5):
            run_dir = notes.run_dir_for(self.runs_root, parts[-2])
            if (
                run_dir
                and len(parts) == 5
                and run_dir.relative_to(self.runs_root).parts != (parts[2], parts[3])
            ):
                run_dir = None  # the project folder in the URL must be the run's real one
        if run_dir is None:
            return self.send_error(404)
        # Only same-machine pages may write (guards against DNS rebinding); cross-site PUTs already fail CORS preflight.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ("localhost", "127.0.0.1", "::1", self.server.server_address[0]):
            return self.send_error(403)
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send_error(415)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.send_error(411)
        if not 0 < length <= notes.MAX_BYTES:
            return self.send_error(413 if length else 411)
        try:
            notes.save(run_dir, self.rfile.read(length))
        except notes.NotesError as e:
            return self.send_error(400, str(e))
        self.send_response(204)
        self.end_headers()

    def end_headers(self):
        if self.path.startswith("/runs/") and self.path.split("?")[0].endswith(".json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):  # quiet
        pass


def cmd_serve(args) -> int:
    dist = _web_dist()
    if dist is None:
        print("Web viewer not built. Run: cd web && bun install && bun run build", file=sys.stderr)
        return 2
    runs_root = Path(args.runs).resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    update_index(runs_root)
    handler = type("Handler", (_Handler,), {"runs_root": runs_root, "web_root": dist})
    server = http.server.ThreadingHTTPServer(
        (args.host, args.port), functools.partial(handler, directory=str(dist))
    )
    url = f"http://{args.host}:{args.port}/"
    print(f"🗺  AppScreenMap viewer → {url}   (runs: {runs_root})  Ctrl+C to stop")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="appscreenmap", description="Map every screen of a mobile app automatically."
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("doctor", help="check adb, devices and optional tools")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("crawl", help="explore an app and build its screen map")
    src = s.add_mutually_exclusive_group(required=True)
    src.add_argument("--apk", help="APK to install and crawl")
    src.add_argument(
        "--app", help="iOS Simulator build (.app folder from an iphonesimulator build) to install and crawl"
    )
    src.add_argument(
        "--package", help="package name (Android) or bundle id (iOS) of an already installed app"
    )
    s.add_argument(
        "--platform",
        choices=["android", "ios"],
        default="android",
        help="android (default) or ios (simulator)",
    )
    s.add_argument("--activity", help="launch activity (default: the app's launcher activity)")
    s.add_argument("--serial", help="device serial, or simulator UDID (default: the only connected device)")
    s.add_argument("--config", help="appscreenmap.toml with budgets, input values, blocked actions")
    s.add_argument("--max-steps", type=int)
    s.add_argument("--max-minutes", type=float)
    s.add_argument("--settle", type=float, help="seconds to wait after each action")
    s.add_argument("--clear-data", action="store_true", help="wipe app data before crawling")
    s.add_argument(
        "--keep-animations",
        action="store_true",
        help="leave system animations on: load times include transitions, as a user sees them",
    )
    s.add_argument("--font-scale", type=float, help="crawl at this system font scale, e.g. 2.0 (WCAG 1.4.4)")
    s.add_argument("--project", help="project folder under runs/ (default: last part of the package)")
    s.add_argument("--name", help="run name prefix (default: the project name)")
    s.add_argument("--out", default="runs", help="runs directory (default: ./runs)")
    s.set_defaults(fn=cmd_crawl)

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

    s = sub.add_parser("mcp", help="serve the maps to agents over MCP (stdio)")
    s.add_argument("--runs", default="runs", help="runs directory (default: ./runs)")
    s.add_argument("--run", help="default run id (default: the latest finished run)")
    s.add_argument("--serial", help="device for where_am_i / go_to_screen / crawl")
    s.set_defaults(fn=cmd_mcp)

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

    s = sub.add_parser(
        "security",
        help="security audit of an Android build (manifest, secrets, data at rest, Frida log) → audits/security.json",
    )
    s.add_argument("run")
    s.add_argument(
        "--apk", help="APK to scan statically (manifest flags, exported components, hard-coded secrets)"
    )
    s.add_argument(
        "--pull", action="store_true", help="scan the installed build: pull its APK from the device"
    )
    s.add_argument(
        "--device",
        action="store_true",
        help="look for secrets left in the app's data folder (debuggable or rooted)",
    )
    s.add_argument("--frida-log", help="output of frida-observe.js (see the security-audit skill)")
    s.add_argument("--serial")
    s.add_argument("--json", action="store_true", help="print the audit as JSON")
    s.set_defaults(fn=cmd_security)

    s = sub.add_parser("report", help="health report for a run: wasted steps, identity issues, failures")
    s.add_argument("run")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("serve", help="open the web viewer")
    s.add_argument("--runs", default="runs")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-open", action="store_true", help="don't open a browser")
    s.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)  # progress shows up live when piped to a file
    try:
        return args.fn(args)
    except DriverError as e:
        print(f"✘ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
