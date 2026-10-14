"""`appscreenmap security`: evidence from separate runs of the scanner is merged; bad input is refused."""

from __future__ import annotations

import json
import plistlib
import zipfile
from argparse import Namespace

from appscreenmap.engine.cli.security import cmd_security
from appscreenmap.security import HOOK

AWS = "AKIA" + "ABCDEFGHIJKLMNOP"  # fake, built at runtime so no scanner flags this file
LOG = """\
{"asm":1,"check":"cleartext","host":"api.old.example.com"}
{"asm":1,"check":"pinning","host":"api.example.com","pins":0,"pinned":false}
"""


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
        "app": None,
        "pull": False,
        "device": False,
        "frida_log": None,
        "frida_script": False,
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
    assert cmd_security(args(run, apk=str(apk))) == 0
    assert cmd_security(args(run, frida_log=str(log))) == 0
    audit = json.loads((run / "audits" / "security.json").read_text())
    rules = {f["id"].split(":")[0] for f in audit["findings"]}
    assert {"hardcoded-secret", "cleartext-observed", "no-cert-pinning"} <= rules
    assert "dynamic" in audit["summary"] and "static" in audit["summary"]
    assert set(json.loads((run / "audits" / "security-evidence.json").read_text())["sources"]) == {
        "apk",
        "frida",
    }


def test_command_refuses_without_input_and_for_ios(tmp_path, capsys):
    assert cmd_security(args(make_run(tmp_path))) == 2
    assert cmd_security(args(make_run(tmp_path / "ios", "ios"), apk="x.apk")) == 2  # iOS needs --app
    assert cmd_security(args(make_run(tmp_path / "ios2", "ios"))) == 2
    assert cmd_security(args(make_run(tmp_path / "droid"), app="x.app")) == 2  # --app is iOS only
    assert cmd_security(args(tmp_path / "missing")) == 2


def test_ios_run_is_audited_from_the_app_bundle(tmp_path, capsys):
    app = tmp_path / "X.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(
        plistlib.dumps(
            {"CFBundleIdentifier": "com.x", "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True}}
        )
    )
    run = make_run(tmp_path / "ios", "ios")
    assert cmd_security(args(run, app=str(app))) == 0
    audit = json.loads((run / "audits" / "security.json").read_text())
    got = {f["id"] for f in audit["findings"]}
    assert got == {"ats-exceptions:arbitrary-loads", "privacy-manifest-missing"}
    assert {f["platform"] for f in audit["findings"]} == {"ios"}


def test_frida_script_prints_the_bundled_hook(capsys):
    assert cmd_security(Namespace(run=None, frida_script=True)) == 0
    assert capsys.readouterr().out.strip() == str(HOOK) and HOOK.is_file()
    assert HOOK.read_text().startswith("// AppScreenMap security audit")
