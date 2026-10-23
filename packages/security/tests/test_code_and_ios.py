"""Dex code checks, the extra manifest rules and the iOS bundle scan."""

from __future__ import annotations

import plistlib
import zipfile
from pathlib import Path

import pytest

from appscreenmap.drivers.apkinfo import find_aapt2
from appscreenmap.security import (
    ats_findings,
    manifest_findings,
    parse_manifest,
    scan_apk,
    scan_code,
    scan_dex_bytes,
    scan_ios_app,
)
from appscreenmap.security.code import CODE_CHECKS
from appscreenmap.security.rules import load_rules
from appscreenmap.testkit.helpers import REPO

AWS = "AKIA" + "ABCDEFGHIJKLMNOP"  # fake, built at runtime so no scanner flags this file


def dex(*strings: str) -> bytes:
    """A stand-in for a dex string table: each string as its length byte, the text and NUL."""
    return b"".join(bytes([len(s)]) + s.encode() + b"\0" for s in strings)


def keys(findings):
    return sorted(f["key"] for f in findings)


# ── dex code checks ──────────────────────────────────────────────────────────
def test_every_check_names_a_ready_rule():
    ready = {r.id for r in load_rules() if r.status == "ready" and r.platform in ("android", "both")}
    assert {c[0] for c in CODE_CHECKS} <= ready


CODE_CASES = [
    (dex("addJavascriptInterface"), "addjavascriptinterface", None),
    (dex("ALLOW_ALL_HOSTNAME_VERIFIER"), "allow-all-hostname-verifier", None),
    (b"Lorg/apache/http/conn/ssl/AllowAllHostnameVerifier;", "allow-all-hostname-verifier", None),
    (dex("DES"), "des", "warning"),
    (dex("DES/CBC/PKCS5Padding"), "des", "warning"),
    (dex("RC4"), "rc4", "warning"),
    (dex("MD5"), "md5", "info"),
    (dex("SHA-1"), "sha-1", "info"),
    (dex("sendStickyBroadcast"), "sendstickybroadcast", None),
    (dex("setAllowFileAccessFromFileURLs"), "setallowfileaccessfromfileurls", None),
    (dex("setAllowFileAccess"), "setallowfileaccess", "info"),
    (b"Ldalvik/system/DexClassLoader;", "dexclassloader", None),
]


def test_each_code_check_fires_on_its_string():
    for data, key, severity in CODE_CASES:
        found = scan_dex_bytes(data, "classes.dex")
        assert keys(found) == [key], key
        assert found[0].get("severity") == severity and "classes.dex" in found[0]["detail"], key


def test_near_misses_are_not_findings():
    # Whole strings only: a longer name, AES, SHA-256 and a safe setter do not match.
    data = dex(
        "addJavascriptInterfaceCompat",
        "AES/GCM/NoPadding",
        "SHA-256",
        "DESCRIPTION",
        "MD5Util",
        "setAllowContentAccess",
    )
    assert scan_dex_bytes(data, "classes.dex") == []


def test_scan_code_reads_every_dex_and_reports_a_check_once(tmp_path):
    apk = tmp_path / "a.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("classes.dex", dex("MD5", "sendStickyBroadcast"))
        z.writestr("classes2.dex", dex("MD5", "RC4"))
        z.writestr("assets/notes.txt", dex("DES"))  # not a dex file
    found = scan_code(apk)
    assert keys(found) == ["md5", "rc4", "sendstickybroadcast"]
    assert next(f for f in found if f["key"] == "md5")["detail"].endswith("classes.dex.")


def test_scan_apk_includes_code_findings_without_aapt2(tmp_path, monkeypatch):
    monkeypatch.setattr("appscreenmap.security.apk.find_aapt2", lambda: None)
    apk = tmp_path / "a.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("classes.dex", dex("RC4"))
    ev = scan_apk(apk)
    assert ev["ran"] == ["static"] and keys(ev["findings"]) == ["rc4"]


# ── manifest: custom permissions, task hijacking ─────────────────────────────
ANDROID = "http://schemas.android.com/apk/res/android"


def tree(min_sdk=24, perms=(), activity_extra=""):
    lines = [
        f"N: android={ANDROID} (line=1)",
        "  E: manifest (line=1)",
        '    A: package="com.example.app" (Raw: "com.example.app")',
        "      E: uses-sdk (line=2)",
        f"        A: {ANDROID}:minSdkVersion(0x0101020c)={min_sdk}",
    ]
    for name, level in perms:
        lines += [
            "      E: permission (line=3)",
            f'        A: {ANDROID}:name(0x01010003)="{name}" (Raw: "{name}")',
        ]
        if level is not None:
            lines.append(f"        A: {ANDROID}:protectionLevel(0x01010009)=0x{level:08x}")
    lines += [
        "      E: application (line=4)",
        "        E: activity (line=5)",
        f'          A: {ANDROID}:name(0x01010003)=".Main" (Raw: ".Main")',
        f"          A: {ANDROID}:exported(0x01010010)=false",
    ]
    if activity_extra:
        lines.append(f"          A: {ANDROID}:{activity_extra}")
    return "\n".join(lines) + "\n"


def test_weak_custom_permissions_are_flagged_and_signature_ones_are_not():
    perms = [
        ("com.example.app.NORMAL", 0),
        ("com.example.app.NOLEVEL", None),
        ("com.example.app.DANGER", 1),
        ("com.example.app.SIG", 2),
    ]
    m = parse_manifest(tree(min_sdk=30, perms=perms))
    assert [p[0].rsplit(".", 1)[-1] for p in m.permissions] == ["NORMAL", "NOLEVEL", "DANGER", "SIG"]
    found = [f for f in manifest_findings(m) if f["rule"] == "custom-permission-weak"]
    assert sorted(f["subject"] for f in found) == ["DANGER", "NOLEVEL", "NORMAL"]


def test_signature_or_system_with_flags_counts_as_signature():
    m = parse_manifest(tree(min_sdk=30, perms=[("com.example.app.P", 0x12)]))  # signature | privileged
    assert not [f for f in manifest_findings(m) if f["rule"] == "custom-permission-weak"]


def test_task_reparenting_is_flagged_but_min_sdk_alone_is_not():
    m = parse_manifest(tree(min_sdk=26, activity_extra="allowTaskReparenting(0x01010204)=true"))
    assert m.min_sdk == 26
    found = [f for f in manifest_findings(m) if f["rule"] == "task-hijacking"]
    assert [f["key"] for f in found] == ["com.example.app.Main"] and "severity" not in found[0]
    assert [
        f for f in manifest_findings(parse_manifest(tree(min_sdk=21))) if f["rule"] == "task-hijacking"
    ] == []


@pytest.mark.skipif(not find_aapt2(), reason="aapt2 not installed")
def test_real_aapt2_output_parses_for_the_new_fields():
    apk = REPO / "samples" / "playground-app" / "apk" / "playground-v1.apk"
    ev = scan_apk(apk)
    # The Playground declares its own permission with protectionLevel signature: not a finding.
    assert not [f for f in ev["findings"] if f["rule"] == "custom-permission-weak"]
    assert ev["package"] == "dev.appscreenmap.playground"


# ── iOS ──────────────────────────────────────────────────────────────────────
def make_app(root: Path, info: dict, privacy=False, executable=b"") -> Path:
    app = root / "X.app"
    app.mkdir(parents=True)
    (app / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleIdentifier": "com.x", "CFBundleExecutable": "X", **info})
    )
    (app / "X").write_bytes(executable)
    if privacy:
        (app / "PrivacyInfo.xcprivacy").write_bytes(plistlib.dumps({"NSPrivacyTracking": False}))
    return app


def test_ats_findings_cover_arbitrary_loads_and_domain_exceptions():
    info = {
        "NSAppTransportSecurity": {
            "NSAllowsArbitraryLoads": True,
            "NSAllowsArbitraryLoadsInWebContent": True,
            "NSExceptionDomains": {
                "legacy.example.com": {"NSExceptionAllowsInsecureHTTPLoads": True},
                "ok.example.com": {"NSExceptionMinimumTLSVersion": "TLSv1.2"},
            },
        }
    }
    got = {f["key"]: f.get("severity") for f in ats_findings(info)}
    assert got == {
        "arbitrary-loads": None,
        "NSAllowsArbitraryLoadsInWebContent": "info",
        "domain:legacy.example.com": "info",
    }
    assert (
        ats_findings({}) == []
        and ats_findings({"NSAppTransportSecurity": {"NSAllowsArbitraryLoads": False}}) == []
    )


def test_clean_app_has_no_findings(tmp_path):
    ev = scan_ios_app(make_app(tmp_path, {}, privacy=True))
    assert ev["findings"] == [] and ev["ran"] == ["manifest", "static"] and ev["package"] == "com.x"


def test_app_folder_findings_and_secret_in_the_binary(tmp_path):
    app = make_app(
        tmp_path,
        {"NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True}},
        executable=b"\x00junk" + AWS.encode() + b"\x00",
    )
    ev = scan_ios_app(app)
    rules = sorted(f["rule"] for f in ev["findings"])
    assert rules == ["ats-exceptions", "hardcoded-secret", "privacy-manifest-missing"]
    secret = next(f for f in ev["findings"] if f["rule"] == "hardcoded-secret")
    assert AWS not in secret["detail"] and "X" in secret["detail"]


def test_ipa_is_read_like_an_app_folder(tmp_path):
    app = make_app(
        tmp_path / "src",
        {"NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True}},
        executable=AWS.encode(),
    )
    ipa = tmp_path / "x.ipa"
    with zipfile.ZipFile(ipa, "w") as z:
        for p in app.rglob("*"):
            z.write(p, f"Payload/X.app/{p.relative_to(app).as_posix()}")
    ev = scan_ios_app(ipa)
    assert sorted(f["rule"] for f in ev["findings"]) == [
        "ats-exceptions",
        "hardcoded-secret",
        "privacy-manifest-missing",
    ]


def test_unreadable_input_is_a_note_not_a_crash(tmp_path):
    bad = tmp_path / "bad.ipa"
    bad.write_bytes(b"not a zip")
    ev = scan_ios_app(bad)
    assert ev["ran"] == [] and ev["findings"] == [] and "did not run" in ev["notes"][0]
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("readme.txt", "x")
    assert "No .app bundle" in scan_ios_app(empty)["notes"][0]
