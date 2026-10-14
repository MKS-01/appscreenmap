"""The crawl writes audits/store.json from the crawled build, and never fails because of it."""

from __future__ import annotations

import json
from argparse import Namespace

from appscreenmap.engine.cli import crawl


class FakeDriver:
    def apk_path(self, package):
        return None


def test_crawl_writes_store_audit_for_an_apk(tmp_path, monkeypatch):
    facts = {"platform": "android", "min_sdk": 26, "target_sdk": 36, "compile_sdk": 36, "notes": []}
    monkeypatch.setattr(crawl, "android_facts", lambda apk: facts)
    audit = crawl._store_audit(tmp_path, Namespace(apk="x.apk", app=None), FakeDriver(), "com.x", False)
    assert audit["status"] == "pass"
    assert json.loads((tmp_path / "audits" / "store.json").read_text())["audit"] == "store"


def test_installed_app_with_no_apk_path_is_skipped_quietly(tmp_path):
    assert crawl._store_audit(tmp_path, Namespace(apk=None, app=None), FakeDriver(), "com.x", False) is None
    assert not (tmp_path / "audits").exists()


def test_unreadable_ios_build_does_not_fail_the_crawl(tmp_path):
    audit = crawl._store_audit(
        tmp_path, Namespace(apk=None, app=str(tmp_path / "nope.app")), None, "com.x", True
    )
    assert audit["status"] == "not_run"
