"""`stack`'s canvas handling: which canvas a scan writes to, and the build it keeps. No device."""

from __future__ import annotations

import json

from appscreenmap.engine.cli.stack import find_canvas, keep_build

PKG = "dev.appscreenmap.playground"


def run(root, project, name, package=PKG, platform=None, scenarios=None):
    d = root / project / name
    d.mkdir(parents=True)
    r = {"id": name, "app": {"package": package}, "device": {"platform": platform} if platform else {}}
    if scenarios:
        r["scenarios"] = scenarios
    (d / "map.json").write_text(json.dumps({"run": r, "screens": []}))
    return d


def test_one_run_is_the_canvas(tmp_path):
    only = run(tmp_path, "playground", "playground-20261027-010000")
    run(tmp_path, "other", "other-20261027-010000", package="dev.example.other")
    assert find_canvas(tmp_path, PKG) == (only, [])


def test_the_merged_run_wins_over_plain_runs(tmp_path):
    run(tmp_path, "playground", "a-20261027-010000")
    canvas = run(tmp_path, "playground", "b-20261027-020000", scenarios=[{"id": "sc1"}])
    assert find_canvas(tmp_path, PKG) == (canvas, [])


def test_ios_runs_of_the_same_bundle_id_are_not_the_android_canvas(tmp_path):
    run(tmp_path, "playground-ios", "ios-20261027-010000", platform="ios")
    assert find_canvas(tmp_path, PKG) == (None, [])


def test_several_plain_runs_are_ambiguous(tmp_path):
    a = run(tmp_path, "playground", "a-20261027-010000")
    b = run(tmp_path, "playground", "b-20261027-020000")
    assert find_canvas(tmp_path, PKG) == (None, [a, b])


def test_the_build_kept_is_the_latest_scan_only(tmp_path):
    canvas = run(tmp_path, "playground", "playground-20261027-010000")
    pulled = tmp_path / "pulled"
    pulled.mkdir()
    (pulled / "base.apk").write_bytes(b"v1")
    (pulled / "split_config.arm64_v8a.apk").write_bytes(b"v1")
    keep_build(canvas, [pulled / "base.apk", pulled / "split_config.arm64_v8a.apk"], "dump v1")
    (pulled / "base.apk").write_bytes(b"v2")
    build = keep_build(canvas, [pulled / "base.apk"], "dump v2")
    assert sorted(p.name for p in (build / "apks").iterdir()) == ["base.apk"]
    assert (build / "apks" / "base.apk").read_bytes() == b"v2"
    assert (build / "dumpsys-package.txt").read_text() == "dump v2"


def test_the_ios_canvas_is_found_by_platform(tmp_path):
    android = run(tmp_path, "playground", "playground-20261027-010000")
    ios = run(tmp_path, "playground-ios", "ios-20261027-010000", platform="ios")
    assert find_canvas(tmp_path, PKG, "ios") == (ios, [])
    assert find_canvas(tmp_path, PKG) == (android, [])


def _sim_app(root):
    """A minimal simulator `.app`: Info.plist and a thin arm64 Mach-O linking Swift and SwiftUI."""
    import plistlib
    import struct

    d = root / "Playground.app"
    d.mkdir(parents=True)
    plist = {
        "CFBundleIdentifier": PKG,
        "CFBundleExecutable": "Playground",
        "CFBundleShortVersionString": "1.0",
    }
    (d / "Info.plist").write_bytes(plistlib.dumps(plist))
    cmds = [struct.pack("<IIIIII", 0x32, 24, 7, 17 << 16, 27 << 16, 0)]
    for lib in ("/usr/lib/swift/libswiftCore.dylib", "/System/Library/Frameworks/SwiftUI.framework/SwiftUI"):
        name = lib.encode() + b"\0"
        name += b"\0" * (-(24 + len(name)) % 8)
        cmds.append(struct.pack("<IIIIII", 0xC, 24 + len(name), 24, 2, 0, 0) + name)
    body = b"".join(cmds)
    (d / "Playground").write_bytes(
        struct.pack("<IIIIIIII", 0xFEEDFACF, 0x0100000C, 0, 2, len(cmds), len(body), 0, 0) + body
    )
    return d


def test_an_ios_scan_makes_its_canvas_in_the_ios_project(tmp_path, monkeypatch):
    """`stack --platform ios` on a stand-in simulator: the `.app` is read and kept, the audit written."""
    from appscreenmap.drivers.base import DriverError
    from appscreenmap.engine.cli import main, stack

    bundle, data = _sim_app(tmp_path / "sim"), tmp_path / "sim" / "data"
    udid = "A1B2C3D4-0000-0000-0000-000000000001"
    monkeypatch.setattr(
        stack.IosSimulatorDriver,
        "list_devices",
        classmethod(lambda cls, run=None: [(udid, "iPhone 17 · iOS 27.0")]),
    )
    monkeypatch.setattr(stack, "app_container", lambda u, b, kind="app": bundle if kind == "app" else data)

    def no_idb(self, udid=None, run=None):
        raise DriverError("idb not found")

    monkeypatch.setattr(stack.IosSimulatorDriver, "__init__", no_idb)
    runs = tmp_path / "runs"
    assert main(["stack", "--platform", "ios", "--package", PKG, "--out", str(runs)]) == 0
    (canvas,) = (runs / "playground-ios").iterdir()
    m = json.loads((canvas / "map.json").read_text())["run"]
    assert m["source"] == "scan" and m["device"]["platform"] == "ios" and m["device"]["model"] == "iPhone 17"
    audit = json.loads((canvas / "audits" / "stack.json").read_text())
    assert audit["summary"] == "Native iOS: Swift, SwiftUI"
    assert audit["facts"]["data_container"] == str(data) and audit["facts"]["min_os"] == "17.0"
    assert (canvas / "build" / "app" / "Playground.app" / "Info.plist").is_file()
    assert find_canvas(runs, PKG) == (None, [])  # the Android canvas is not this one
    assert (
        main(["stack", "--platform", "ios", "--package", PKG, "--out", str(runs)]) == 0
    )  # rescan: same canvas
    assert [canvas] == list((runs / "playground-ios").iterdir())


def test_an_ios_scan_without_a_booted_simulator_fails_fast(tmp_path, monkeypatch, capsys):
    from appscreenmap.engine.cli import main, stack

    monkeypatch.setattr(stack.IosSimulatorDriver, "list_devices", classmethod(lambda cls, run=None: []))
    assert main(["stack", "--platform", "ios", "--package", PKG, "--out", str(tmp_path / "runs")]) == 2
    assert "No booted iOS simulator" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists()
