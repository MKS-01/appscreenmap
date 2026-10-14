"""`appscreenmap verify`: replay every recorded path on a (fake) new build."""

import json
import shutil
from pathlib import Path

import pytest

from appscreenmap.core.model import load_map
from appscreenmap.crawler import explorer as explorer_mod
from appscreenmap.crawler import replay as replay_mod
from appscreenmap.regression.verify import plan, update_baselines, verify_run
from appscreenmap.testkit.fakedevice import NAV, SCREENS, FakeApp, FakeDriver, btn, crawl, title
from appscreenmap.testkit.helpers import hierarchy, node

# Three levels deep, so a broken first step blocks a screen behind it.
APP = {
    **SCREENS,
    "settings": hierarchy(
        title("Settings"),
        btn((900, 150, 1040, 260), desc="Close settings"),
        btn((100, 400, 1000, 500), text="Advanced"),
    ),
    "advanced": hierarchy(
        title("Advanced"), node("android.widget.TextView", (40, 300, 1000, 360), text="Logs")
    ),
}
APP_NAV = {**NAV, ("settings", "Advanced"): "advanced"}


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(explorer_mod, "PIN_TOAST_SECONDS", 0)
    monkeypatch.setattr(replay_mod, "PIN_TOAST_SECONDS", 0)


@pytest.fixture(scope="module")
def crawled(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setattr(explorer_mod, "PIN_TOAST_SECONDS", 0)
    run_dir, _ = crawl(tmp_path_factory.mktemp("base"), FakeDriver(FakeApp(APP, APP_NAV)))
    mp.undo()
    return run_dir


@pytest.fixture
def base(crawled, tmp_path):
    """A fresh copy of the crawled base run per test (verify writes into it)."""
    return Path(shutil.copytree(crawled, tmp_path / "proj" / crawled.name))


def ids(run_dir):
    return {s["title"]: s["id"] for s in load_map(run_dir)["screens"] if s["kind"] == "app"}


def by_title(rep, run_dir):
    sid = {v: k for k, v in ids(run_dir).items()}
    return {sid[r["screen"]]: r for r in rep["screens"]}


def test_plan_replays_longest_paths_first(base):
    targets, skipped = plan(load_map(base))
    i = ids(base)
    assert targets[0] == i["Advanced"] and skipped == {}
    assert set(targets) == set(i.values())


def test_same_build_passes_every_screen(base):
    d = FakeDriver(FakeApp(APP, APP_NAV))
    rep = verify_run(base, d, log=lambda *a: None)
    assert rep["ok"] and rep["status"] == "done"
    assert rep["summary"]["passed"] == 4 and rep["summary"]["failed"] == 0
    assert rep["summary"]["changed"] == 0
    # Shorter paths were checked on the way: Home → Settings → Advanced, then About.
    assert d.app.taps == ["Settings", "Advanced", "About"]
    assert not d.pinned  # unpinned when done
    out = json.loads((base / "verify" / rep["id"] / "verify.json").read_text())
    assert out["summary"] == rep["summary"]
    adv = by_title(out, base)["Advanced"]
    assert adv["path"] == [ids(base)["Home"], ids(base)["Settings"]] and adv["via"] == "key"
    assert (base / "verify" / rep["id"] / adv["screenshot"]).is_file()


def test_missing_element_fails_its_screen_and_blocks_the_ones_behind_it(base):
    renamed = {**APP, "home": APP["home"].replace('text="Settings"', 'text="Preferences"')}
    nav = {**APP_NAV, ("home", "Preferences"): "settings"}
    rep = verify_run(base, FakeDriver(FakeApp(renamed, nav, version="2.0")), log=lambda *a: None)
    assert not rep["ok"]
    r = by_title(rep, base)
    assert r["Settings"]["status"] == "failed"
    f = r["Settings"]["failure"]
    assert f["reason"] == "not_found" and f["label"] == "Settings" and f["on"] == ids(base)["Home"]
    assert f["screenshot"] and f["hierarchy"]
    assert r["Advanced"]["status"] == "blocked" and r["Advanced"]["blocked_by"] == ids(base)["Settings"]
    assert r["About"]["status"] == "passed"
    # Home's text changed, so it passes but is reported as visually changed.
    assert r["Home"]["status"] == "passed" and r["Home"]["changed"]
    assert r["Home"]["visual"]["text"]["changed"] == 1


def test_step_to_the_wrong_screen_fails(base):
    nav = {**APP_NAV, ("home", "About"): "settings"}
    rep = verify_run(base, FakeDriver(FakeApp(APP, nav)), log=lambda *a: None)
    about = by_title(rep, base)["About"]
    assert about["status"] == "failed"
    assert about["failure"]["reason"] == "wrong_screen" and about["failure"]["got"] == ids(base)["Settings"]


def test_launch_on_another_screen_blocks_everything(base):
    rep = verify_run(base, FakeDriver(FakeApp(APP, APP_NAV, start="about")), log=lambda *a: None)
    s = rep["summary"]
    # Every path starts at launch, so nothing else is replayed once launch itself is wrong.
    assert s["failed"] == 1 and s["blocked"] == 3 and s["passed"] == 0
    home = by_title(rep, base)["Home"]
    assert home["failure"]["reason"] == "not_launched" and home["failure"]["action"] == "launch"


def test_clear_data_follows_the_base_run(tmp_path):
    run_dir, _ = crawl(tmp_path, FakeDriver(FakeApp(APP, APP_NAV)), clear_data=True)
    d = FakeDriver(FakeApp(APP, APP_NAV))
    verify_run(run_dir, d, log=lambda *a: None)
    assert d.cleared == 2  # one launch per replayed path (Advanced, About)
    d2 = FakeDriver(FakeApp(APP, APP_NAV))
    verify_run(run_dir, d2, clear_data=False, log=lambda *a: None)
    assert d2.cleared == 0


def test_update_baselines_accepts_the_new_look(base):
    changed = {**APP, "about": APP["about"].replace("Version 1.0", "Build 1.0")}
    rep = verify_run(base, FakeDriver(FakeApp(changed, APP_NAV)), log=lambda *a: None)
    about_id = ids(base)["About"]
    assert by_title(rep, base)["About"]["changed"]
    before = next(s for s in load_map(base)["screens"] if s["id"] == about_id)["tokens"]
    assert about_id in update_baselines(base, rep)
    after = next(s for s in load_map(base)["screens"] if s["id"] == about_id)
    assert after["tokens"] != before and "T:build #.#" in after["tokens"]
    assert "Build 1.0" in (base / after["hierarchy"]).read_text()
    rep2 = verify_run(base, FakeDriver(FakeApp(changed, APP_NAV)), log=lambda *a: None)
    assert rep2["summary"]["changed"] == 0


def _edit_map(run_dir, fn):
    data = load_map(run_dir)
    fn({s["title"]: s for s in data["screens"] if s["kind"] == "app"})
    (run_dir / "map.json").write_text(json.dumps(data))


def test_screens_sharing_a_path_are_skipped_not_failed(base):
    # Two screens behind the same steps: which one opens depends on app state (seen on sample-app: two
    # 'FOLLOWING' states behind Following → Done). Replaying the path can't pick between them.
    _edit_map(base, lambda s: s["About"].update(reach_path=s["Settings"]["reach_path"]))
    rep = verify_run(base, FakeDriver(FakeApp(APP, APP_NAV)), log=lambda *a: None)
    about = by_title(rep, base)["About"]
    assert about["status"] == "skipped" and ids(base)["Settings"] in about["note"]
    assert rep["ok"] and rep["summary"]["failed"] == 0


def test_step_on_an_element_the_crawl_saw_only_later_is_state_dependent(base):
    # sample-app: '14:59 / OPEN' only exists while a focus timer runs (started by an earlier tap that
    # stayed on the same screen). The base capture of the screen doesn't have it, so a fresh launch
    # can't replay the path: skip with evidence instead of failing an unchanged build.
    def timer_step(s):
        step = s["About"]["reach_path"][0]
        step.update(key="click|View||##:## / open", label="14:59 / OPEN", selector={"point": [540, 1800]})

    _edit_map(base, timer_step)
    rep = verify_run(base, FakeDriver(FakeApp(APP, APP_NAV)), log=lambda *a: None)
    about = by_title(rep, base)["About"]
    assert about["status"] == "skipped" and "app state" in about["note"]
    assert about["failure"]["reason"] == "wrong_screen" and about["failure"]["screenshot"]
    assert rep["ok"]


def test_a_removed_element_the_base_capture_had_still_fails(base):
    renamed = {**APP, "home": APP["home"].replace('text="About"', 'text="Info"')}
    rep = verify_run(
        base, FakeDriver(FakeApp(renamed, {**APP_NAV, ("home", "Info"): "about"})), log=lambda *a: None
    )
    assert by_title(rep, base)["About"]["status"] == "failed" and not rep["ok"]


# An element that only appears after a same-screen step: 'OPEN' shows once '15 MIN' starts a timer.
HOME_T = APP["home"].replace(
    "</node></hierarchy>", btn((600, 300, 1000, 420), text="15 MIN") + "</node></hierarchy>"
)
TIMER_APP = {
    **APP,
    "home": HOME_T,
    "home_timer": HOME_T.replace(
        "</node></hierarchy>", btn((100, 700, 1000, 820), text="OPEN") + "</node></hierarchy>"
    ),
}
TIMER_NAV = {**APP_NAV, ("home", "15 MIN"): "home_timer", ("home_timer", "OPEN"): "about"}


def _revealed_path(base):
    """Rewrite the base map as a crawl with `revealed_by` records it: About is reached by
    15 MIN (same screen) → OPEN, and Home has a field the crawl typed into."""

    def edit(s):
        home = s["Home"]
        mk = lambda label, x: {
            "screen": home["id"],
            "key": f"click|Button||{label.lower()}",
            "action": "click",
            "label": label,
            "selector": {"text": label, "point": [x, 360]},
            "scroll_depth": 0,
        }
        start, open_ = (
            mk("15 MIN", 800),
            {**mk("OPEN", 550), "selector": {"text": "OPEN", "point": [550, 760]}},
        )
        s["About"]["reach_path"] = [start, open_]
        home["elements"].append(
            {
                **open_,
                "kind": "button",
                "rid": "",
                "text": "OPEN",
                "desc": "",
                "bounds": [100, 700, 1000, 820],
                "status": "done",
                "revealed_by": [start],
            }
        )
        home["autofill"] = [
            {"key": "k", "label": "Name", "rid": "", "value": "typed-once", "selector": {"point": [10, 10]}}
        ]

    _edit_map(base, edit)


def test_revealed_by_steps_replay_and_autofill_once_per_screen(base):
    _revealed_path(base)
    d = FakeDriver(FakeApp(TIMER_APP, TIMER_NAV))
    about = ids(base)["About"]
    replay_mod.Replayer(d, load_map(base), log=lambda *a: None).replay(about)
    assert d.app.taps == ["15 MIN", "OPEN"] and d.app.screen == "about"
    assert d.app.typed == ["typed-once"]  # not typed again before the second step on Home


def test_missing_element_with_revealed_by_is_a_real_failure(base):
    # The crawl knew how to reveal OPEN; if the steps run and it still isn't there, the build changed.
    _revealed_path(base)
    nav = {k: v for k, v in TIMER_NAV.items() if k != ("home", "15 MIN")}
    rep = verify_run(base, FakeDriver(FakeApp(TIMER_APP, nav)), log=lambda *a: None)
    about = by_title(rep, base)["About"]
    assert about["status"] == "failed" and about["failure"]["label"] == "OPEN"
