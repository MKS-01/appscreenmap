from __future__ import annotations

import plistlib
import zipfile
from datetime import date

from appscreenmap.store import build_audit, ios_facts, parse_android_sdk, parse_ios_plist

TREE = """N: android=http://schemas.android.com/apk/res/android
  E: manifest (line=2)
    A: http://schemas.android.com/apk/res/android:versionCode(0x0101021b)=1
    A: http://schemas.android.com/apk/res/android:compileSdkVersion(0x01010572)=35
    A: package="com.example.app" (Raw: "com.example.app")
    A: platformBuildVersionCode=35
    E: uses-sdk (line=7)
      A: http://schemas.android.com/apk/res/android:minSdkVersion(0x0101020c)=24
      A: http://schemas.android.com/apk/res/android:targetSdkVersion(0x01010270)=35
    E: application (line=9)
"""
TODAY = date(2026, 10, 15)


def ids(audit):
    return {f["id"]: f for f in audit["findings"]}


def android(target, compile_sdk, **kw):
    facts = {
        "platform": "android",
        "min_sdk": 24,
        "target_sdk": target,
        "compile_sdk": compile_sdk,
        "notes": [],
    }
    return ids(build_audit(facts, TODAY, **kw))


def test_parse_android_sdk():
    f = parse_android_sdk(TREE)
    assert (f["package"], f["min_sdk"], f["target_sdk"], f["compile_sdk"]) == ("com.example.app", 24, 35, 35)


def test_compile_sdk_falls_back_to_platform_build_version():
    f = parse_android_sdk(TREE.replace("compileSdkVersion(0x01010572)=35", "x=1"))
    assert f["compile_sdk"] == 35


def test_target_35_in_extension_window_is_due():
    f = android(35, 35)["store::target-36"]
    assert (f["severity"], f["requirement"], f["due"]) == ("error", "due", "2026-11-01")
    assert android(35, 35)["store::target-35"]["requirement"] == "met"
    assert android(35, 35)["store::compile-behind"]["requirement"] == "due"


def test_target_35_after_extension_is_blocked():
    audit = ids(
        build_audit(
            {"platform": "android", "target_sdk": 35, "compile_sdk": 35, "notes": []}, date(2026, 11, 2)
        )
    )
    assert audit["store::target-36"]["requirement"] == "blocked"


def test_target_36_passes_and_next_is_always_listed():
    audit = build_audit(
        {"platform": "android", "min_sdk": 26, "target_sdk": 36, "compile_sdk": 36, "notes": []}, TODAY
    )
    assert audit["status"] == "pass"
    assert "store::next" in ids(audit)


def test_upcoming_requirement_inside_the_year_is_flagged_before_it_bites():
    f = ids(
        build_audit(
            {"platform": "android", "target_sdk": 35, "compile_sdk": 35, "notes": []}, date(2026, 6, 1)
        )
    )
    assert f["store::target-36"]["requirement"] == "upcoming"
    assert f["store::target-36"]["severity"] == "warning"


def test_tiers_beyond_the_horizon_are_hidden():
    f = ids(
        build_audit(
            {"platform": "android", "target_sdk": 34, "compile_sdk": 34, "notes": []}, date(2025, 1, 1)
        )
    )
    assert "store::target-36" not in f and "store::target-35" in f


def test_old_target_loses_availability_and_compile_below_target_warns():
    f = android(33, 31)
    assert f["store::availability"]["requirement"] == "due"
    assert f["store::compile-below-target"]["severity"] == "warning"


def test_wear_floor_is_lower():
    f = android(35, 35, form_factor="wear")
    assert f["store::target-35"]["requirement"] == "met"
    assert "store::target-36" not in f


def test_unknown_compile_sdk_is_not_guessed():
    f = android(36, None)
    assert f["store::compile-unknown"]["requirement"] == "not_checked"


def info(sdk="iphoneos26.0", xcode="2601", minos="16.0"):
    return {"CFBundleIdentifier": "com.x", "DTSDKName": sdk, "DTXcode": xcode, "MinimumOSVersion": minos}


def ios(**kw):
    return ids(build_audit(parse_ios_plist(info(**kw)), TODAY))


def test_ios_parse():
    f = parse_ios_plist(info())
    assert (f["sdk_major"], f["xcode"], f["deployment_major"]) == (26, "26.0.1", 16)


def test_ios_old_sdk_is_blocked():
    f = ios(sdk="iphoneos18.5", xcode="1641")
    assert (f["store::sdk"]["severity"], f["store::sdk"]["requirement"]) == ("error", "blocked")


def test_ios_current_sdk_and_deployment_pass():
    f = ios()
    assert f["store::sdk"]["requirement"] == "met" and f["store::deployment"]["requirement"] == "met"
    assert "store::next" in f


def test_ios_deployment_below_13_is_blocked():
    assert ios(minos="12.0")["store::deployment"]["requirement"] == "blocked"


def test_ios_simulator_build_is_noted():
    assert "store::simulator-build" in ios(sdk="iphonesimulator26.0")


def test_ios_facts_from_app_folder_and_ipa(tmp_path):
    app = tmp_path / "A.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(plistlib.dumps(info(), fmt=plistlib.FMT_BINARY))
    assert ios_facts(app)["sdk_major"] == 26
    ipa = tmp_path / "A.ipa"
    with zipfile.ZipFile(ipa, "w") as z:
        z.writestr("Payload/A.app/Info.plist", plistlib.dumps(info(minos="15.0")))
    assert ios_facts(ipa)["deployment_major"] == 15


def test_unreadable_build_is_not_a_pass():
    audit = build_audit(ios_facts("/nonexistent.ipa"), TODAY)
    assert audit["status"] == "not_run" and audit["score"] is None


def test_only_open_requirements_carry_a_timeline_date():
    audit = build_audit(
        {"platform": "android", "min_sdk": 24, "target_sdk": 35, "compile_sdk": 35, "notes": []}, TODAY
    )
    dated = {f["id"]: f["requirement"] for f in audit["findings"] if "due" in f}
    assert dated and all(r != "met" for r in dated.values())
