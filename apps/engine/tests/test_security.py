"""The security scanner: manifest rules, secret scanning, data at rest, Frida log, and the audit it writes."""

from __future__ import annotations

import json
import zipfile
from argparse import Namespace
from pathlib import Path

import pytest
from helpers import REPO

from appscreenmap import cli
from appscreenmap.apkinfo import find_aapt2
from appscreenmap.security import (
    build_audit,
    manifest_findings,
    parse_frida_log,
    parse_manifest,
    parse_network_config,
    resource_file,
    scan_apk,
    scan_bytes,
    scan_device_data,
    scan_secrets,
)
from appscreenmap.security_rules import load_rules

FIX = Path(__file__).parent / "fixtures"
MANIFEST = (FIX / "insecure_manifest.xmltree.txt").read_text()
NSC = (FIX / "insecure_nsc.xmltree.txt").read_text()
RESOURCES = (FIX / "insecure_resources.txt").read_text()

# Fake credentials, built at runtime so no scanner flags this file.
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
STRIPE = "sk_" + "live_" + "a1b2c3d4e5f6g7h8i9j0k1l2"
GOOGLE = "AIza" + "SyA-1234567890abcdefghijklmnopqrstu"


def ids(findings):
    return sorted(
        f["rule"] + (":" + f["key"].rsplit(".", 1)[-1] if f["rule"] == "exported-component" else "")
        for f in findings
    )


# ── manifest ─────────────────────────────────────────────────────────────────
def test_manifest_flags_and_components_are_parsed():
    m = parse_manifest(MANIFEST)
    assert (m.package, m.target_sdk) == ("com.example.insecure", 26)
    assert m.debuggable is True and m.allow_backup is True and m.cleartext is True
    assert m.network_config == "@0x7f010000"
    by = {c.name.rsplit(".", 1)[-1]: c for c in m.components}
    assert by["Main"].is_launcher and by["Main"].exposed
    assert by["Deep"].exported is None and by["Deep"].exposed  # intent filter, no android:exported
    assert by["Guarded"].permission == "android.permission.DUMP"


def test_network_config_and_resource_lookup():
    assert resource_file(RESOURCES, "@0x7f010000") == "res/xml/network_security_config.xml"
    assert resource_file(RESOURCES, "@0x7f990000") is None
    nsc = parse_network_config(NSC)
    assert nsc == {"base_cleartext": False, "cleartext_domains": ["legacy.example.com"]}


def test_insecure_manifest_findings():
    m = parse_manifest(MANIFEST)
    found = manifest_findings(m, parse_network_config(NSC))
    assert ids(found) == [
        "allow-backup",
        "cleartext-traffic",  # the domain-scoped one: the config's base-config forbids it app-wide
        "debuggable",
        "exported-component:Deep",
        "exported-component:Files",
        "exported-component:Sync",
    ]
    cleartext = next(f for f in found if f["rule"] == "cleartext-traffic")
    assert cleartext["severity"] == "info" and "legacy.example.com" in cleartext["detail"]
    # The launcher activity and the receiver guarded by a permission are not findings.
    assert not any("Main" in f.get("key", "") or "Guarded" in f.get("key", "") for f in found)


def test_cleartext_defaults_follow_the_target_sdk():
    base = 'E: manifest (line=1)\n  A: package="p"\n  E: uses-sdk (line=2)\n    A: android:targetSdkVersion(0x01010270)={sdk}\n  E: application (line=3)\n    A: android:allowBackup(0x01010280)=false\n'
    old = manifest_findings(parse_manifest(base.format(sdk=26)))
    new = manifest_findings(parse_manifest(base.format(sdk=34)))
    assert [f["rule"] for f in old] == ["cleartext-traffic"] and "below 28" in old[0]["detail"]
    assert new == []


def test_app_widget_providers_are_a_note_but_extra_actions_still_warn():
    tpl = (
        'E: manifest (line=1)\n  A: package="p"\n  E: application (line=2)\n    A: android:allowBackup(0x01010280)=false\n'
        '      E: receiver (line=3)\n        A: android:name(0x01010003)=".W"\n        A: android:exported(0x01010010)=true\n'
        "          E: intent-filter (line=4)\n            E: action (line=5)\n"
        '              A: android:name(0x01010003)="android.appwidget.action.APPWIDGET_UPDATE"\n{extra}'
    )
    only = manifest_findings(parse_manifest(tpl.format(extra="")))
    extra = '            E: action (line=6)\n              A: android:name(0x01010003)="p.REFRESH"\n'
    more = manifest_findings(parse_manifest(tpl.format(extra=extra)))
    assert only[0]["severity"] == "info" and "severity" not in more[0]


# ── secrets ──────────────────────────────────────────────────────────────────
def test_secrets_are_found_but_their_values_never_kept():
    blob = b"\x00\x14" + AWS.encode() + b"\x00" + STRIPE.encode() + b"\x00" + GOOGLE.encode() + b"\x00"
    found = scan_bytes(blob, "classes.dex")
    kinds = {f["subject"]: f["severity"] for f in found}
    assert kinds == {
        "AWS access key id": "error",
        "Stripe live secret key": "error",
        "Google API key": "info",
    }
    dumped = json.dumps(found)
    assert AWS not in dumped and STRIPE not in dumped and GOOGLE not in dumped
    assert "sha256" in dumped and "classes.dex" in dumped


def test_documented_example_keys_and_plain_words_are_ignored():
    blob = b"AKIAIOSFODNN7EXAMPLE password=hunter2 api_key client_secret Bearer abc"
    assert scan_bytes(blob, "x") == []


def test_scan_secrets_reads_dex_assets_and_resources_once(tmp_path):
    apk = tmp_path / "a.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("classes.dex", b"..." + AWS.encode())
        z.writestr("classes2.dex", b"..." + AWS.encode())  # same secret again: one finding
        z.writestr("assets/config.json", b'{"u": "postgres://app:s3cretpass@db.internal/prod"}')
        z.writestr("lib/arm64-v8a/libx.so", b"..." + STRIPE.encode())  # native libs are not scanned
    found = scan_secrets(apk)
    assert sorted(f["subject"] for f in found) == ["AWS access key id", "Database URL with credentials"]
    assert "s3cretpass" not in json.dumps(found)


@pytest.mark.skipif(not find_aapt2(), reason="aapt2 not installed")
def test_a_clean_release_apk_has_no_findings():
    ev = scan_apk(REPO / "samples/playground-app/apk/playground-v1.apk")
    assert ev["ran"] == ["manifest", "static"] and ev["findings"] == []


# ── data at rest ─────────────────────────────────────────────────────────────
class FakeDevice:
    def __init__(self, files: dict[str, str] | None):
        self.files = files

    def run_as(self, package, command):
        if self.files is None:
            return None
        if command.startswith("find"):
            return "\n".join(self.files) + "\n"
        return self.files[command.split("'")[1]]


PREFS = (
    "<?xml version='1.0' encoding='utf-8'?><map>"
    '<string name="access_token">tok-abcdef123456</string><string name="theme">dark</string>'
    '<string name="password">x</string><boolean name="auth_enabled" value="true" /></map>'
)


def test_secrets_at_rest_in_shared_prefs_are_reported_without_values():
    ev = scan_device_data(FakeDevice({"shared_prefs/session.xml": PREFS}), "com.x")
    assert ev["ran"] == ["data"]
    assert [f["key"] for f in ev["findings"]] == ["shared_prefs/session.xml:access_token"]
    assert "tok-abcdef123456" not in json.dumps(
        ev
    )  # 'password' is too short to be a secret; 'theme' isn't secret-named


def test_an_unreadable_data_folder_is_reported_as_not_run():
    ev = scan_device_data(FakeDevice(None), "com.x")
    assert ev["ran"] == [] and ev["findings"] == [] and "isn't readable" in ev["notes"][0]


# ── Frida log ────────────────────────────────────────────────────────────────
LOG = """\
Spawned `com.x`. Resuming main thread!
{"asm":1,"check":"cleartext","host":"api.old.example.com"}
{"asm":1,"check":"cleartext","host":"api.old.example.com"}
{"asm":1,"check":"pinning","host":"api.example.com","pins":0,"pinned":false}
{"asm":1,"check":"pinning","host":"pay.example.com","pins":2,"pinned":true}
{"asm":1,"check":"pinning","host":"unknown.example.com","pins":-1,"pinned":null}
{"asm":1,"check":"hook-failed","what":"okhttp3.Foo"}
{"other":"json"}
"""


def test_frida_log_becomes_findings():
    ev = parse_frida_log(LOG)
    assert ev["ran"] == ["dynamic"]
    assert sorted((f["rule"], f.get("key", "")) for f in ev["findings"]) == [
        ("cleartext-observed", "api.old.example.com"),
        ("no-cert-pinning", ""),
    ]
    pin = ev["findings"][-1]["detail"]
    assert "api.example.com" in pin and "pay.example.com" not in pin and "unknown.example.com" not in pin
    assert "okhttp3.Foo" in ev["notes"][0]
    assert parse_frida_log("nothing observed")["ran"] == []


# ── the audit ────────────────────────────────────────────────────────────────
def test_audit_uses_rule_text_scores_and_never_reads_as_a_pass():
    found = manifest_findings(parse_manifest(MANIFEST), parse_network_config(NSC)) + scan_bytes(
        AWS.encode(), "classes.dex"
    )
    audit = build_audit({"apk": {"ran": ["manifest", "static"], "notes": [], "findings": found}})
    assert audit["audit"] == "security" and audit["source"] == "run" and audit["status"] == "fail"
    assert (
        audit["score"] == 100 - 20 * 2 - 8 * 4 - 2 * 1
    )  # debuggable + secret; backup + 3 exported; domain cleartext
    assert audit["findings"][0]["severity"] == "error"
    rules = {r.id: r for r in load_rules()}
    for f in audit["findings"]:
        rule = rules[f["id"].split(":")[0]]
        assert f["fix"] == rule.fix and f["refs"][0]["url"] == rule.refs[0].url
    assert "not run: data, dynamic" in audit["summary"]

    clean = build_audit({"apk": {"ran": ["manifest", "static"], "notes": [], "findings": []}})
    assert clean["status"] == "info" and clean["score"] == 100  # unchecked rules remain, so never "pass"


# ── the command ──────────────────────────────────────────────────────────────
def make_run(tmp_path, platform="android"):
    run = tmp_path / "run"
    run.mkdir(parents=True)
    (run / "map.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "run": {
                    "id": "r",
                    "app": {"package": "com.x", "label": "X", "platform": platform},
                    "device": {"platform": platform},
                },
                "screens": [],
                "transitions": [],
            }
        )
    )
    return run


def args(run, **kw):
    base = {
        "run": str(run),
        "apk": None,
        "pull": False,
        "device": False,
        "frida_log": None,
        "serial": None,
        "json": False,
    }
    return Namespace(**{**base, **kw})


def test_command_merges_evidence_from_separate_runs_of_the_scanner(tmp_path, capsys):
    run = make_run(tmp_path)
    apk = tmp_path / "a.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("classes.dex", AWS.encode())
    log = tmp_path / "frida.log"
    log.write_text(LOG)
    assert cli.cmd_security(args(run, apk=str(apk))) == 0
    assert cli.cmd_security(args(run, frida_log=str(log))) == 0
    audit = json.loads((run / "audits" / "security.json").read_text())
    rules = {f["id"].split(":")[0] for f in audit["findings"]}
    assert {"hardcoded-secret", "cleartext-observed", "no-cert-pinning"} <= rules
    assert "dynamic" in audit["summary"] and "static" in audit["summary"]
    assert set(json.loads((run / "audits" / "security-evidence.json").read_text())["sources"]) == {
        "apk",
        "frida",
    }


def test_command_refuses_without_input_and_for_ios(tmp_path, capsys):
    assert cli.cmd_security(args(make_run(tmp_path))) == 2
    assert cli.cmd_security(args(make_run(tmp_path / "ios", "ios"), apk="x.apk")) == 2
    assert cli.cmd_security(args(tmp_path / "missing")) == 2
