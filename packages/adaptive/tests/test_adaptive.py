"""Static adaptive rules on synthetic manifests and Info.plists: no device, no aapt2."""

from __future__ import annotations

import json
from datetime import date

from appscreenmap.adaptive import build_audit, load_rules, parse_manifest, parse_plist, write_audit

NS = "http://schemas.android.com/apk/res/android"


def _tree(activities: str, target: int = 36, app_attrs: str = "") -> str:
    """The shape `aapt2 dump xmltree` prints (the Playground's manifest, trimmed)."""
    return f"""N: android={NS} (line=2)
  E: manifest (line=2)
    A: package="dev.alpha" (Raw: "dev.alpha")
      E: uses-sdk (line=7)
        A: {NS}:minSdkVersion(0x0101020c)=26
        A: {NS}:targetSdkVersion(0x01010270)={target}
      E: application (line=21)
        A: {NS}:label(0x01010001)=@0x7f080003
{app_attrs}{activities}"""


def _act(name: str, *attrs: str) -> str:
    lines = [
        "          E: activity (line=29)",
        f'            A: {NS}:name(0x01010003)="{name}" (Raw: "{name}")',
    ]
    lines += [f"            A: {NS}:{a}" for a in attrs]
    lines += ["              E: intent-filter (line=33)", "                  E: action (line=34)"]
    return "\n".join(lines) + "\n"


HANDLES_SIZE = "configChanges(0x0101001f)=(type 0x11)0xda0"  # orientation|screenLayout|screenSize|smallestScreenSize|keyboardHidden


def _ids(audit):
    return [f["id"] for f in audit["findings"]]


def test_playground_locked_activity_is_flagged_with_the_api_37_date():
    tree = _tree(
        _act("dev.alpha.MainActivity", HANDLES_SIZE)
        + _act("dev.alpha.ScannerActivity", "screenOrientation(0x0101001e)=1", HANDLES_SIZE)
    )
    facts = parse_manifest(tree)
    assert facts["target_sdk"] == 36
    audit = build_audit(facts, date(2026, 10, 28))
    f = next(f for f in audit["findings"] if f["id"] == "adaptive::orientation-locked")
    assert f["items"] == ["ScannerActivity → portrait"]
    # targetSdk 36: Android 16 already ignores the lock on large screens (no opt-out declared)
    assert f["requirement"] == "ignored on large screens" and "due" not in f
    assert f["official_id"] == "Config_Changes" and f["tier"] == "ready" and f["refs"]
    assert audit["status"] == "warn" and _ids(audit) == ["adaptive::orientation-locked"]


def test_every_static_android_rule():
    tree = _tree(
        _act(".Locked", "screenOrientation(0x0101001e)=(type 0x10)0xc")
        + _act(".Nosensor", "screenOrientation(0x0101001e)=5", HANDLES_SIZE)
        + _act(".Fixed", "resizeableActivity(0x010104f6)=(type 0x12)0x0", HANDLES_SIZE)
        + _act(".Wide", "maxAspectRatio(0x01010540)=(type 0x4)2.1", HANDLES_SIZE)
    )
    audit = build_audit(parse_manifest(tree), date(2026, 10, 28))
    assert _ids(audit) == [
        "adaptive::aspect-ratio-limited",
        "adaptive::orientation-locked",
        "adaptive::orientation-nosensor",
        "adaptive::resize-disabled",
        "adaptive::recreated-on-resize",
    ]
    by = {f["id"]: f for f in audit["findings"]}
    assert by["adaptive::orientation-locked"]["items"] == ["Locked → userPortrait"]
    assert by["adaptive::aspect-ratio-limited"]["items"] == ["Wide: max 2.1"]
    assert by["adaptive::recreated-on-resize"]["items"] == ["Locked"]  # relative names resolve; info only
    assert by["adaptive::recreated-on-resize"]["severity"] == "info"


def test_app_level_resize_off_applies_to_every_activity():
    tree = _tree(
        _act(".A", HANDLES_SIZE), app_attrs=f"        A: {NS}:resizeableActivity(0x010104f6)=false\n"
    )
    f = build_audit(parse_manifest(tree), date(2026, 10, 28))["findings"][0]
    assert f["id"] == "adaptive::resize-disabled" and f["items"] == ["A"]


def test_android_17_timing_and_games():
    tree = _tree(_act(".L", "screenOrientation(0x0101001e)=1", HANDLES_SIZE), target=35)
    late = build_audit(parse_manifest(tree), date(2027, 9, 1))["findings"][0]
    assert late["severity"] == "error" and late["requirement"] == "blocked"
    now = build_audit(
        parse_manifest(_tree(_act(".L", "screenOrientation(0x0101001e)=1", HANDLES_SIZE), target=37))
    )
    assert now["findings"][0]["requirement"] == "ignored on large screens" and "due" not in now["findings"][0]
    game = _tree(_act(".L", "screenOrientation(0x0101001e)=0", HANDLES_SIZE),
                 app_attrs=f"        A: {NS}:appCategory(0x01010545)=0\n")  # fmt: skip
    g = build_audit(parse_manifest(game), date(2026, 10, 28))
    assert g["findings"][0]["severity"] == "info" and g["status"] == "pass"


def test_clean_manifest_passes_and_lists_manual_and_size_checks():
    audit = build_audit(parse_manifest(_tree(_act(".A", HANDLES_SIZE))), date(2026, 10, 28))
    assert audit["findings"] == [] and audit["status"] == "pass" and audit["score"] == 100
    assert {m["id"] for m in audit["manual"]} >= {"keyboard", "fold-continuity", "postures"}
    assert "duo-displays" not in {m["id"] for m in audit["manual"]}
    assert "size checks need a crawl" in audit["summary"]


def test_unreadable_build_is_not_run():
    audit = build_audit({"platform": "android", "notes": ["aapt2 not found"]})
    assert audit["status"] == "not_run" and audit["score"] is None and audit["summary"] == "aapt2 not found"


def test_ios_static_rules():
    facts = parse_plist({
        "UIRequiresFullScreen": True, "UIDeviceFamily": [1], "DTXcode": "2601",
        "UISupportedInterfaceOrientations": ["UIInterfaceOrientationPortrait"],
    })  # fmt: skip
    audit = build_audit(facts)
    assert _ids(audit) == [
        "adaptive::ios-built-before-duo",
        "adaptive::ios-no-scenes",
        "adaptive::ios-requires-fullscreen",
        "adaptive::ios-iphone-only",
        "adaptive::ios-portrait-only",
    ]
    assert "Xcode 26" in audit["findings"][0]["detail"]
    assert "duo-displays" in {m["id"] for m in audit["manual"]}
    ok = build_audit(
        parse_plist({"UIApplicationSceneManifest": {}, "UIDeviceFamily": [1, 2], "DTXcode": "2710"})
    )
    assert ok["findings"] == [] and ok["status"] == "pass"


def test_catalogue_is_well_formed():
    cat = load_rules()
    ids = [r["id"] for r in cat["rules"]]
    assert len(ids) == len(set(ids))
    for r in cat["rules"]:
        assert r["detect"] in ("static", "condition", "manual") and r["platform"] in ("android", "ios", "any")
        assert r["tier"] in ("ready", "optimized", "differentiated", "hig")
        assert all(k in cat["sources"] for k in r["refs"]), r["id"]
        assert r["detect"] != "static" or (r.get("why") and r.get("fix")), r["id"]
        assert r["detect"] != "manual" or r.get("steps"), r["id"]
    assert all(s["url"].startswith("https://developer.") for s in cat["sources"].values())


def test_writes_the_standard_audit_file(tmp_path):
    p = write_audit(tmp_path, build_audit(parse_manifest(_tree(_act(".A")))))
    a = json.loads(p.read_text())
    assert p.name == "adaptive.json" and a["schema"] == 1 and a["audit"] == "adaptive"
    assert isinstance(a["findings"], list) and a["title"] == "Adaptive UI"
