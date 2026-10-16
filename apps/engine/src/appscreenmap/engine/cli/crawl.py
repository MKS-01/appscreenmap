"""Check the setup and crawl an app: `doctor`, `crawl`."""

from __future__ import annotations

import os
import shutil
import signal
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from appscreenmap.a11y.checks import audit_run
from appscreenmap.a11y.report import write_reports
from appscreenmap.core import __version__, accounts, activity, locales
from appscreenmap.core.config import CrawlConfig
from appscreenmap.core.model import AppMap
from appscreenmap.core.runs import new_run_dir, update_index
from appscreenmap.crawler.explorer import CrawlAborted, Explorer
from appscreenmap.drivers.android import AdbDriver
from appscreenmap.drivers.apkinfo import apk_info, find_aapt2
from appscreenmap.drivers.base import DriverError
from appscreenmap.drivers.device import describe
from appscreenmap.exporters.export import export_run
from appscreenmap.reports.perf import summarize as summarize_perf
from appscreenmap.store import android_facts, build_audit, ios_facts
from appscreenmap.store import write_audit as write_store_audit

from .serve import _web_dist


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
        print(f"  {'ok' if good else 'fail':<5} {label}{' · ' + detail if detail else ''}")

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
        str(dist) if dist else "run `bun install && make viewer`",
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
        print(f"installing {apk.name} ({package})")
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
        print(f"installing {bundle.name} ({package})")
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


def _store_audit(run_dir: Path, args, d, package: str, ios: bool) -> dict | None:
    """Write audits/store.json from the crawled build's SDK levels. Never fails a crawl; None if it couldn't run."""
    try:
        if ios:
            facts = ios_facts(args.app) if args.app else None
        elif args.apk:
            facts = android_facts(args.apk)
        else:  # crawled an installed app: read the SDK levels from a pulled copy of its APK
            remote = d.apk_path(package)
            facts = None
            if remote:
                with tempfile.TemporaryDirectory() as tmp:
                    d.pull(remote, Path(tmp) / "base.apk")
                    facts = android_facts(Path(tmp) / "base.apk")
        if facts is None:
            return None
        audit = build_audit(facts)
        write_store_audit(run_dir, audit)
        return audit
    except (DriverError, OSError, ValueError, KeyError) as e:
        print(f"  store readiness skipped: {e}", file=sys.stderr)
        return None


def _apply_locale(d, package: str, cfg: CrawlConfig, device: dict) -> dict:
    """Put the app in `cfg.locale` (when asked), and say so when we have no safety words for the language it is shown in."""
    shown = cfg.locale or ((device.get("settings") or {}).get("locale") or "")
    out: dict = {"requested": cfg.locale or None, "applied": False, "before": "", "shown": shown or None}
    if cfg.locale:
        try:
            out["before"] = d.get_app_locales(package)
            out["applied"] = d.set_app_locales(package, cfg.locale)
        except DriverError as e:
            print(f"  could not set the app language: {e}", file=sys.stderr)
        if out["applied"]:
            print(f"app language: {cfg.locale}")
        else:
            print(
                f"  ! could not set the app language to {cfg.locale} (Android 13+ is needed, and the app must have "
                "that language); the crawl continues in whatever language the app shows.",
                file=sys.stderr,
            )
    out["words_for_language"] = locales.covers(shown)
    if not out["words_for_language"]:
        print(
            f"  ! no safety words for the language '{shown}': buttons like log out, delete or pay in that language "
            "are not recognised. Add them under [safety] blocked_text in your config.",
            file=sys.stderr,
        )
    return out


def cmd_crawl(args) -> int:
    cfg = CrawlConfig.load(
        args.config,
        max_steps=args.max_steps,
        max_minutes=args.max_minutes,
        clear_data=True if args.clear_data else None,
        settle_seconds=args.settle,
        font_scale=args.font_scale,
        locale=args.locale,
        disable_animations=False if args.keep_animations else None,
    )
    if missing := cfg.missing_secrets():
        print(
            f"Set {', '.join(missing)} in the environment: [inputs] uses them as ${{NAME}} placeholders.",
            file=sys.stderr,
        )
        return 2
    activity.add_secrets(os.environ.get(n) for n in cfg.secret_names())
    ios = bool(args.app) or args.platform == "ios"
    if ios:
        cfg.measure_load = (
            False  # load timing reads Android's frame counters; iOS has no equivalent wired yet
        )
    setup = (_setup_ios if ios else _setup_android)(args, cfg)
    if isinstance(setup, int):
        return setup
    d, app, package, launch = setup

    if cfg.uses_account():
        acct = accounts.load_or_create(package, cfg.account_email)
        os.environ.update(accounts.env_for(acct))
        activity.add_secrets([acct["password"]])
        print(
            f"test account: {acct['email']} ({'new, saved to' if acct['new'] else 'reusing'} {acct['path']}; "
            f"status {acct['status']})"
        )

    original_font_scale = None
    if cfg.font_scale:
        original_font_scale = d.get_font_scale()
        d.set_font_scale(cfg.font_scale)

    runs_root = Path(args.out)
    # Android and iOS builds of one app have different screens: keep their runs in separate project folders.
    project = args.project or (f"{package.rsplit('.', 1)[-1]}-ios" if ios else None)
    run_dir = new_run_dir(runs_root, package, args.name, project)
    activity.bind_run(run_dir)
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
        f"mapping {app.get('label')} {app.get('version') or ''} on {run['device']['name']} ({run['device']['type']}) into {run_dir}"
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
    original_locale = None
    run["locale"] = _apply_locale(d, package, cfg, run["device"])
    if run["locale"]["applied"]:
        original_locale = run["locale"].pop("before")
    run["locale"].pop("before", None)
    amap.save(run_dir / "map.json")

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
        print("\nstopped: saving what we have")
    except CrawlAborted as e:
        run["status"] = "failed"
        run["error"] = str(e)
        print(f"error: {e}", file=sys.stderr)
        code = 1
    except DriverError as e:
        run["status"] = "failed"
        run["error"] = str(e)
        print(f"device error: {e}", file=sys.stderr)
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
        if original_locale is not None:
            try:
                d.set_app_locales(package, original_locale)
            except DriverError:
                pass
        run["finished_at"] = _now()
        explorer.save()
        export = export_run(run_dir)
        audit = audit_run(run_dir)
        write_reports(run_dir)
        store = _store_audit(run_dir, args, d, package, ios)
        perf = summarize_perf(run_dir, budget_ms=cfg.perf_budget_ms)
        update_index(runs_root)
    st = amap.stats()
    print(
        f"\ndone: {st['screens']} screens, {st['transitions']} transitions, {st['crashes']} crashes, "
        f"{run['steps']} steps in {run['elapsed_s']:.0f}s"
    )
    if st["activity_coverage"] is not None:
        print(f"  activity coverage: {st['activity_coverage']:.0%} of {st['activities_declared']} declared")
    print(f"  {export['flows']} Maestro flows in {run_dir / 'flows'}")
    if perf["screens"]:
        slowest = perf["screens"][0]
        print(
            f"  slowest screen: {slowest['screen']} '{slowest['title']}' {slowest['median_ms']} ms "
            f"(median); {len(perf['findings'])} perf finding(s): appscreenmap perf {run_dir}"
        )
    print(f"  {audit['summary']['issues']} WCAG 2.2 findings: {run_dir / 'a11y-report.html'}")
    if store and store["status"] != "not_run":
        print(f"  store readiness: {store.get('status_label') or store['status']}: {store['summary']}")
    print(f"  view it: appscreenmap serve --runs {runs_root}")
    return code


def register(sub) -> None:
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
    s.add_argument(
        "--locale",
        help="crawl the app in this language, e.g. fr-FR, ja, ar (Android 13+; iOS relaunches the app). "
        "Pseudo-locales en-XA and ar-XB test long text and right-to-left layouts",
    )
    s.add_argument("--font-scale", type=float, help="crawl at this system font scale, e.g. 2.0 (WCAG 1.4.4)")
    s.add_argument("--project", help="project folder under runs/ (default: last part of the package)")
    s.add_argument("--name", help="run name prefix (default: the project name)")
    s.add_argument("--out", default="runs", help="runs directory (default: ./runs)")
    s.set_defaults(fn=cmd_crawl)
