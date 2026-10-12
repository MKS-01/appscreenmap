"""End-to-end crawl against a fake device: a tiny three-screen app, no emulator needed."""

import json

import pytest
from fakedevice import ACT, FakeDriver
from helpers import PKG

from appscreenmap import explorer as explorer_mod
from appscreenmap.config import CrawlConfig
from appscreenmap.explorer import Explorer
from appscreenmap.model import AppMap
from appscreenmap.perf import summarize


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(explorer_mod, "PIN_TOAST_SECONDS", 0)


def test_full_crawl_on_fake_app(tmp_path):
    cfg = CrawlConfig(
        max_steps=60, settle_seconds=0, launch_wait_seconds=0, load_quiet_ms=40, load_timeout_s=2
    )
    run_dir = tmp_path / "proj" / "proj-1"
    run_dir.mkdir(parents=True)
    d = FakeDriver()
    amap = AppMap(
        {
            "id": "proj-1",
            "app": {"package": PKG},
            "device": {"width": 1080, "height": 2400},
            "config": cfg.to_dict(),
        }
    )
    ex = Explorer(d, PKG, ACT, cfg, run_dir, amap, log=lambda *a: None)
    ex.run()

    titles = {s.title for s in amap.screens.values() if s.kind == "app"}
    assert titles == {"Home", "Settings", "About"}
    assert ex.stop_reason == "complete: nothing left to explore"
    edges = {
        (amap.screens[t.src].title, t.label, amap.screens[t.dst].title) for t in amap.transitions.values()
    }
    assert ("Home", "Settings", "Settings") in edges and ("Settings", "Close settings", "Home") in edges
    assert all(e.status != "pending" for s in amap.screens.values() for e in s.elements.values())
    # Never left the app, BACK on the root was a no-op (pinned), and nothing outside it was registered.
    assert not [s for s in amap.screens.values() if s.kind != "app"]

    # Load timings recorded on real (non-inferred) navigation edges, plus cold start.
    to_settings = next(t for t in amap.transitions.values() if t.label == "Settings")
    assert to_settings.timings and to_settings.timings[0]["settled"]
    assert amap.perf["startup"][0]["TotalTime"] == 640

    data = json.loads((run_dir / "map.json").read_text())
    assert data["run"]["stop_reason"] == ex.stop_reason and data["perf"]["startup"]
    assert (run_dir / "trace.jsonl").read_text().count("\n") >= 4
    rep = summarize(run_dir, budget_ms=1000)
    assert {r["title"] for r in rep["screens"]} >= {"Settings", "About"}


def _explorer(tmp_path, **cfg_kw):
    cfg = CrawlConfig(
        max_steps=60, settle_seconds=0, launch_wait_seconds=0, load_quiet_ms=40, load_timeout_s=2, **cfg_kw
    )
    run_dir = tmp_path / "proj" / "proj-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    amap = AppMap(
        {
            "id": "proj-1",
            "app": {"package": PKG},
            "device": {"width": 1080, "height": 2400},
            "config": cfg.to_dict(),
        }
    )
    return Explorer(FakeDriver(), PKG, ACT, cfg, run_dir, amap, log=lambda *a: None), amap


def test_screens_get_an_origin_and_orphans_heal(tmp_path):
    ex, _ = _explorer(tmp_path)
    ex.restart("start")
    home = ex.cur
    assert home.origin == "launch" and home.reach_path == []

    # A screen first seen outside a recorded action (e.g. after returning from another app).
    ex.d.app.screen = "about"
    about, is_new = ex.arrive()
    assert is_new and about.origin == "unknown" and about.reach_path == []

    # Later a known screen leads there: the orphan gets a real path.
    ex.d.app.screen = "home"
    ex.arrive()
    el = next(e for e in home.elements.values() if e.info.label == "About")
    ex.act(el, explore=True)
    assert ex.cur is about and about.origin == "action" and about.depth == 1
    assert [st.label for st in about.reach_path] == ["About"]


def test_launch_landing_on_a_restored_screen_is_an_entry_point(tmp_path, monkeypatch):
    ex, _ = _explorer(tmp_path)
    monkeypatch.setattr(ex.d, "force_stop", lambda pkg: setattr(ex.d.app, "screen", "settings"))
    ex.restart("start")
    assert ex.cur.title == "Settings" and ex.cur.origin == "launch" and ex.cur.depth == 0


def test_export_skips_screens_without_a_path(tmp_path):
    from appscreenmap.export import export_run

    ex, _ = _explorer(tmp_path)
    ex.restart("start")
    ex.d.app.screen = "about"
    ex.arrive()  # orphan
    ex.save()
    res = export_run(ex.dir)
    assert res["skipped"] == ["s002"] and res["flows"] == 1
    assert not (ex.dir / "flows" / "s002.yaml").exists()


from fakedevice import SCREENS, FakeApp
from fakedevice import btn as _btn
from helpers import hierarchy, node

from appscreenmap.driver import Snapshot

SIGNIN_SCREENS = {
    "signin": hierarchy(
        node("android.widget.TextView", (40, 150, 600, 220), text="Welcome back", rid=f"{PKG}:id/title"),
        _btn((100, 300, 980, 420), text="Sign in"),
        _btn((100, 500, 980, 620), text="Forgot password?"),
    ),
    "forgot": hierarchy(
        node("android.widget.TextView", (40, 150, 600, 220), text="Reset password", rid=f"{PKG}:id/title"),
        _btn((100, 300, 980, 420), text="Send link"),
    ),
    "home": SCREENS["home"],
    "settings": SCREENS["settings"],
    "about": SCREENS["about"],
}


class SignInApp(FakeApp):
    """Signing in persists (like SharedPreferences): launch then skips the sign-in screen."""

    def __init__(self):
        super().__init__()
        self.screens = SIGNIN_SCREENS
        self.signed_in, self.screen = False, "signin"

    def tap(self, x, y):
        if self.screen == "signin":
            if 300 <= y <= 420:
                self.signed_in, self.screen, self.stack = True, "home", []
            elif 500 <= y <= 620:
                self.stack.append("signin")
                self.screen = "forgot"
            self.frames += 10
            return
        super().tap(x, y)


def test_data_reset_reaches_first_run_screens(tmp_path, monkeypatch):
    monkeypatch.setattr(explorer_mod, "PIN_TOAST_SECONDS", 0)
    for clear_data, expect_forgot in ((True, True), (False, False)):
        ex, amap = _explorer(tmp_path / str(clear_data), clear_data=clear_data)
        app = SignInApp()
        ex.d.app = app
        ex.d.snapshot = lambda retries=3, a=app: Snapshot(SIGNIN_SCREENS[a.screen], PKG, ACT)
        ex.d.force_stop = lambda pkg, a=app: (
            setattr(a, "screen", "home" if a.signed_in else "signin") or a.stack.clear()
        )
        ex.d.clear_data = lambda pkg, a=app: setattr(a, "signed_in", False)
        ex.d.grant_all = lambda pkg: None
        ex.run()
        titles = {s.title for s in amap.screens.values() if s.kind == "app"}
        assert ("Reset password" in titles) is expect_forgot, (clear_data, titles)
        assert any(e["type"] == "data_reset" for e in amap.events) is clear_data
