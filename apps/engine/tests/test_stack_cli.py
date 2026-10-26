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
