"""`security`: the security audit of an Android or iOS build (see appscreenmap.security)."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from appscreenmap.core.model import load_map
from appscreenmap.drivers.android import AdbDriver
from appscreenmap.security import (
    HOOK,
    load_evidence,
    parse_frida_log,
    scan_apk,
    scan_device_data,
    scan_ios_app,
    write_audit,
)


def cmd_security(args) -> int:
    if args.frida_script:
        print(HOOK)
        return 0
    if not args.run:
        print(
            "Which run? appscreenmap security <run> --apk FILE (Android: or --pull, --device, --frida-log) or --app FILE (iOS).",
            file=sys.stderr,
        )
        return 2
    run = Path(args.run)
    if not (run / "map.json").is_file():
        print(f"Not a run directory (no map.json): {run}", file=sys.stderr)
        return 2
    data = load_map(run)
    app = data["run"]["app"]
    if (app.get("platform") or data["run"]["device"].get("platform")) == "ios":
        if not args.app:
            print("iOS run: pass --app FILE (the .app folder or the .ipa).", file=sys.stderr)
            return 2
        if args.apk or args.pull or args.device or args.frida_log:
            print("--apk, --pull, --device and --frida-log are Android only.", file=sys.stderr)
            return 2
        sources = load_evidence(run)
        sources["ios-app"] = {**scan_ios_app(args.app), "at": datetime.now(UTC).isoformat(timespec="seconds")}
        return _report(run, app, write_audit(run, sources, "ios"), args.json)
    if args.app:
        print("--app is for iOS runs; use --apk for Android.", file=sys.stderr)
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
    return _report(run, app, write_audit(run, sources), args.json)


def _report(run: Path, app: dict, audit: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(audit, indent=1))
        return 0
    print(
        f"security audit for {app.get('label') or app['package']}: score {audit['score']}, {audit['summary']}"
    )
    for f in audit["findings"]:
        print(f"  {f['severity']:7} {f['title']}")
    for m in audit["metrics"]:
        if m["label"] == "note":
            print(f"  ! {m['value']}")
    print(f"report: {run / 'audits' / 'security.json'}  (Insights, then Security, in `appscreenmap serve`)")
    return 0


def register(sub) -> None:
    s = sub.add_parser(
        "security",
        help="security audit of an Android or iOS build (manifest, code, secrets, data at rest, Frida log), written to audits/security.json",
    )
    s.add_argument("run", nargs="?")
    s.add_argument(
        "--apk", help="APK to scan statically (manifest flags, components, risky API use, hard-coded secrets)"
    )
    s.add_argument(
        "--app", help="iOS .app folder or .ipa to scan statically (Info.plist, privacy manifest, secrets)"
    )
    s.add_argument(
        "--pull", action="store_true", help="scan the installed build: pull its APK from the device"
    )
    s.add_argument(
        "--device",
        action="store_true",
        help="look for secrets left in the app's data folder (debuggable or rooted)",
    )
    s.add_argument(
        "--frida-log", help="what the Frida hook printed (see --frida-script and the security-audit skill)"
    )
    s.add_argument(
        "--frida-script",
        action="store_true",
        help="print the path of the bundled Frida hook (frida -l …) and exit",
    )
    s.add_argument("--serial")
    s.add_argument("--json", action="store_true", help="print the audit as JSON")
    s.set_defaults(fn=cmd_security)
