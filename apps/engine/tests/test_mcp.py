"""The MCP server: map queries without a device, device tools against the fake app."""

import json
import shutil
from pathlib import Path

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from appscreenmap.a11y.checks import audit_run
from appscreenmap.core.model import load_map
from appscreenmap.crawler import explorer as explorer_mod
from appscreenmap.crawler import replay as replay_mod
from appscreenmap.crawler.replay import Replayer
from appscreenmap.engine.mcp_server import MapTools, build_server, shortest_path
from appscreenmap.reports.perf import summarize
from appscreenmap.testkit.fakedevice import FakeDriver, crawl, title
from appscreenmap.testkit.helpers import hierarchy


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(explorer_mod, "PIN_TOAST_SECONDS", 0)
    monkeypatch.setattr(replay_mod, "PIN_TOAST_SECONDS", 0)


@pytest.fixture(scope="module")
def crawled(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setattr(explorer_mod, "PIN_TOAST_SECONDS", 0)
    runs = tmp_path_factory.mktemp("runs")
    run_dir, _ = crawl(runs, FakeDriver())
    audit_run(run_dir)
    summarize(run_dir)
    mp.undo()
    return run_dir


@pytest.fixture
def tools(crawled, tmp_path):
    runs = tmp_path / "runs"
    shutil.copytree(crawled.parent.parent, runs)
    return MapTools(runs)


def sid(tools, title):
    return next(s["id"] for s in tools.list_screens()["screens"] if s["title"] == title)


def test_list_runs_and_screens(tools):
    runs = tools.list_runs()["runs"]
    assert [r["id"] for r in runs] == ["proj-1"] and runs[0]["screens"] == 3
    assert {s["title"] for s in tools.list_screens()["screens"]} == {"Home", "Settings", "About"}
    assert tools.list_runs(project="other")["runs"] == []


def test_find_screens_by_title_and_element_label(tools):
    assert tools.find_screens("settings")["screens"][0]["title"] == "Settings"
    hit = tools.find_screens("dark mode")["screens"][0]
    assert hit["title"] == "Settings" and hit["matched"] == "element 'Dark mode'"
    assert tools.find_screens("nothing like this")["screens"] == []


def test_get_screen_explains_elements_and_paths(tools):
    s = tools.get_screen("About")  # a title works as well as an id
    assert s["how_to_reach"] == ["on s001 'Home': tap 'About'"]
    assert {"from": "s001", "label": "About"} in s["reached_from"]
    home = tools.get_screen("s001")
    assert home["how_to_reach"] == ["it is the launch screen"]
    about = next(e for e in home["elements"] if e["label"] == "About")
    assert about["target"] == s["id"] and about["status"] == "done"
    assert home["files"]["screenshot"] and Path(home["files"]["screenshot"]).is_file()
    with pytest.raises(ValueError, match="list_screens"):
        tools.get_screen("s999")


def test_route_from_launch_and_between_screens(tools):
    r = tools.route("Settings")
    assert r["from"] == "launch" and [st["label"] for st in r["steps"]] == ["Settings"]
    assert r["steps"][0]["to"] == sid(tools, "Settings")
    r2 = tools.route("About", from_screen="Settings")
    assert [st["label"] for st in r2["steps"]] == ["Close settings", "About"]
    assert r2["instructions"][0].startswith(f"on {sid(tools, 'Settings')} 'Settings': tap 'Close settings'")
    # About's only way out is the system Back the crawl recorded.
    assert [st["action"] for st in tools.route("Settings", from_screen="About")["steps"]] == ["back", "click"]


def test_shortest_path_prefers_forward_edges():
    data = {
        "screens": [{"id": i, "kind": "app"} for i in ("a", "b", "c")],
        "transitions": [
            {"from": "a", "to": "c", "kind": "back", "action": "back", "key": "k1", "label": "Back"},
            {"from": "a", "to": "b", "kind": "button", "action": "click", "key": "k2", "label": "B"},
            {"from": "b", "to": "c", "kind": "button", "action": "click", "key": "k3", "label": "C"},
        ],
    }
    assert [t["key"] for t in shortest_path(data, "a", "c")] == ["k2", "k3"]  # 2 taps beat 1 Back
    assert shortest_path(data, "c", "a") is None


def test_reports(tools):
    rep = tools.a11y_findings()
    assert rep["standard"] == "WCAG 2.2" and rep["level"] == "AA"
    assert all(f["level"] in ("A", "AA") for f in rep["findings"])
    assert sum(r["issues"] for r in rep["screens"]) == rep["issues"]
    perf = tools.perf_summary()
    assert perf["budget_ms"] == 1000 and {p["title"] for p in perf["screens"]} >= {"Settings"}


def test_where_am_i_and_go_to_screen_on_the_fake_device(tools, monkeypatch):
    d = FakeDriver()
    monkeypatch.setattr(tools, "_replayer", lambda data, serial: Replayer(d, data, log=lambda *a: None))
    d.app.screen = "settings"
    here = tools.where_am_i()
    assert here["in_app"] and here["title"] == "Settings" and here["similarity"] == 1.0
    assert "Dark mode" in here["visible"]

    res = tools.go_to_screen("About")  # Settings → Close → Home → About, no relaunch
    assert res["reached"] and res["via"] == "transitions" and d.app.screen == "about"
    assert not d.pinned
    assert tools.go_to_screen("About")["via"] == "already there"

    # On a screen the map doesn't know: relaunch and replay the recorded path.
    d.app.screens = {**d.app.screens, "splash": hierarchy(title("What's new"))}
    d.app.screen = "splash"
    assert tools.where_am_i()["screen"] is None
    res = tools.go_to_screen("Settings")
    assert res["reached"] and res["via"] == "relaunch" and d.app.screen == "settings"


def test_server_registers_tools_and_reports_errors(tools):
    server = build_server(tools)

    async def go():
        listed = {t.name: t for t in await server.list_tools()}
        assert {"find_screens", "route", "where_am_i", "go_to_screen", "a11y_findings", "screenshot"} <= set(
            listed
        )
        assert listed["get_screen"].annotations.read_only_hint is True
        assert listed["go_to_screen"].annotations.destructive_hint is True
        ok = await server.call_tool("find_screens", {"query": "about"})
        assert not ok.is_error and json.loads(ok.content[0].text)["screens"][0]["title"] == "About"
        # A ToolError (not a crash): the protocol layer sends its message to the agent as an error result.
        with pytest.raises(ToolError, match="see list_screens") as err:
            await server.call_tool("get_screen", {"screen": "s999"})
        assert not isinstance(err.value, UnexpectedToolError)
        img = await server.call_tool("screenshot", {"screen": "s001"})
        assert img.content[0].type == "image"

    anyio.run(go)


def test_crawl_status_reads_the_run_from_the_log(tools, tmp_path, monkeypatch):
    import subprocess
    import sys
    import time

    run_dir = next(iter((tools.runs_root / "proj").iterdir()))
    log = tmp_path / "crawl.log"
    log.write_text(f"mapping Fake 1.0 on Fake into {run_dir}\n[  1] s001 · click 'About'\n")
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    tools._jobs["crawl-x"] = {"proc": proc, "log": log, "started": time.time()}
    st = tools.crawl_status()
    assert st["status"] == "done" and st["run"] == "proj-1" and st["screens"] == 3
    assert load_map(run_dir)["run"]["status"] == st["run_status"]


def test_transition_steps_include_revealed_by():
    from appscreenmap.engine.mcp_server import transition_steps

    start = {
        "screen": "a",
        "key": "k0",
        "action": "click",
        "label": "15 MIN",
        "selector": {},
        "scroll_depth": 0,
    }
    data = {
        "screens": [
            {
                "id": "a",
                "kind": "app",
                "elements": [
                    {
                        "key": "k1",
                        "label": "OPEN",
                        "text": "OPEN",
                        "bounds": [0, 0, 10, 10],
                        "revealed_by": [start],
                    }
                ],
            },
            {"id": "b", "kind": "app", "elements": []},
        ],
        "transitions": [],
    }
    t = {"from": "a", "to": "b", "key": "k1", "action": "click", "label": "OPEN", "kind": "button"}
    steps = transition_steps(data, [t])
    assert [(s["label"], s["to"]) for s in steps] == [("15 MIN", "a"), ("OPEN", "b")]


def test_crawl_log_run_dir_line_old_and_new():
    from appscreenmap.engine.mcp_server import _RUN_DIR_RE

    new = "mapping Playground 1.0 on Pixel (emulator) into runs/playground/playground-v1-1"
    old = "🗺  mapping Playground 1.0 on Pixel (emulator) → runs/playground/playground-v1-1"
    assert (
        _RUN_DIR_RE.search(new).group(1)
        == _RUN_DIR_RE.search(old).group(1)
        == "runs/playground/playground-v1-1"
    )
