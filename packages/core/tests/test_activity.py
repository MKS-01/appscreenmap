"""The activity log: every line a command prints lands in the shared stream and the run's log.txt, secrets masked."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

from appscreenmap.core import activity


def _events(root):
    return [json.loads(line) for line in activity.stream_path(root).read_text().splitlines()]


def test_source_is_the_launchers_then_the_agents_then_ci():
    assert activity.detect_source({"APPSCREENMAP_SOURCE": "mcp", "CLAUDECODE": "1"}) == "mcp"
    assert activity.detect_source({"CLAUDECODE": "1"}) == "agent"
    assert activity.detect_source({"AI_AGENT": "some-agent"}) == "agent"
    assert activity.detect_source({"CI": "true"}) == "ci"
    assert activity.detect_source({"APPSCREENMAP_SOURCE": "nonsense"}) == "cli"
    assert activity.detect_source({}) == "cli"


def test_levels():
    assert activity.level_of("error: no device", "stderr") == "error"
    assert activity.level_of("  ! screenshot failed", "stdout") == "warn"
    assert activity.level_of("could not set the app language", "stderr") == "warn"
    assert activity.level_of("  new screen s004", "stdout") == "info"


def test_captured_lines_reach_the_stream_and_the_run_log(tmp_path):
    root, run = tmp_path / "runs", tmp_path / "runs" / "app" / "app-20261016-120000"
    run.mkdir(parents=True)
    log = activity.ActivityLog(root, "crawl", source="agent", env={})
    streams = SimpleNamespace(stdout=io.StringIO(), stderr=io.StringIO())
    with activity.capture(log, streams):
        print("installing app.apk", file=streams.stdout)  # before the run exists
        activity.bind_run(run)
        print("  new screen s001", file=streams.stdout)
        print(file=streams.stdout)  # blank lines are skipped
        print("  ! no safety words", file=streams.stderr)
        streams.stdout.write("no newline at the end")
    assert activity.current() is None
    ev = _events(root)
    msgs = [e["msg"].strip() for e in ev]
    assert msgs == ["installing app.apk", "new screen s001", "! no safety words", "no newline at the end"]
    assert ev[0]["run"] is None and ev[1]["run"] == run.name
    assert {e["source"] for e in ev} == {"agent"} and {e["cmd"] for e in ev} == {"crawl"}
    assert ev[2]["level"] == "warn"
    text = (run / activity.RUN_LOG).read_text()
    assert "installing app.apk" in text and "new screen s001" in text  # the early line was copied in
    assert "installing app.apk" in streams.stdout.getvalue()  # the terminal still gets everything


def test_secrets_are_masked_everywhere(tmp_path):
    log = activity.ActivityLog(tmp_path, "crawl", env={"APP_PASSWORD": "playground-demo", "HOME": "/Users/x"})
    log.add_secrets(["Asm-s3cret-9!", "ab"])  # too short to mask: would hit ordinary words
    out = io.StringIO()
    streams = SimpleNamespace(stdout=out, stderr=io.StringIO())
    with activity.capture(log, streams):
        print("typing playground-demo and Asm-s3cret-9! into ab", file=streams.stdout)
    raw = activity.stream_path(tmp_path).read_text()
    for where in (raw, out.getvalue()):
        assert "playground-demo" not in where and "Asm-s3cret-9!" not in where
        assert activity.MASK in where and "into ab" in where


def test_output_is_capped_and_ansi_stripped(tmp_path):
    log = activity.ActivityLog(tmp_path, "report", env={}, max_lines=3)
    for i in range(10):
        log.line(f"\x1b[31mline {i}\x1b[0m")
    msgs = [e["msg"] for e in _events(tmp_path)]
    assert msgs[:3] == ["line 0", "line 1", "line 2"]
    assert len(msgs) == 4 and "not logged" in msgs[3]


def test_the_stream_rotates(tmp_path):
    log = activity.ActivityLog(tmp_path, "crawl", env={}, max_bytes=400)
    for i in range(20):
        log.line(f"step {i} " + "x" * 40)
    path = activity.stream_path(tmp_path)
    assert path.with_name(path.name + ".1").is_file()
    assert path.stat().st_size < 400 + 300


def test_read_events_follows_appends_and_rotation(tmp_path):
    log = activity.ActivityLog(tmp_path, "crawl", env={})
    path = activity.stream_path(tmp_path)
    assert activity.read_events(path) == ([], 0)
    log.line("one")
    ev, off = activity.read_events(path)
    assert [e["msg"] for e in ev] == ["one"]
    with path.open("a") as f:
        f.write('{"msg": "half')  # a line still being written waits for its newline
    assert activity.read_events(path, off) == ([], off)
    with path.open("a") as f:
        f.write('"}\n')
    ev, off = activity.read_events(path, off)
    assert [e["msg"] for e in ev] == ["half"]
    path.write_text('{"msg": "new"}\n')  # rotated underneath us: read the new file from the top
    ev, _ = activity.read_events(path, off)
    assert [e["msg"] for e in ev] == ["new"]


def _ev(pid, t, msg, kind=None, **kw):
    e = {"t": f"2026-10-16T12:00:{t:02d}.000+00:00", "cmd": "crawl", "run": None, "source": "agent", "level": "info"}
    e.update(msg=msg, pid=pid, **kw)
    if kind:
        e["kind"] = kind
    return e


def test_sessions_group_a_command_run_and_say_how_it_ended():
    events = [
        _ev(1, 0, "appscreenmap crawl --apk a.apk", "start"),
        _ev(2, 1, "appscreenmap security run", "start", cmd="security", source="cli"),
        _ev(1, 2, "new screen s001", run="p-1"),
        _ev(2, 3, "! no network security config", level="warn", cmd="security", source="cli", run="p-1"),
        _ev(2, 4, "exit 1 after 0.2s", "end", level="error", cmd="security", source="cli", run="p-1", exit=1),
        _ev(3, 5, "orphan line: its start rotated away"),
    ]
    ss = activity.sessions(events, alive=lambda pid: pid == 1, now=_ts_of(events[-1]) + 5)
    crawl, sec, orphan = ss
    assert crawl["status"] == "running" and crawl["run"] == "p-1" and crawl["command"].endswith("a.apk")
    assert crawl["lines"] == 1 and crawl["last"] == "new screen s001" and not crawl["recent"]
    assert sec["status"] == "failed" and sec["exit"] == 1 and sec["warnings"] == 1 and sec["recent"]
    assert orphan["status"] == "interrupted" and orphan["command"] == ""
    assert activity.sessions(events, alive=lambda p: False)[0]["status"] == "interrupted"  # killed, no end
    old = [_ev(4, 0, "appscreenmap perf", "start"), _ev(4, 1, "exit 0 after 0.0s", "end")]  # no "exit" field yet
    assert activity.sessions(old)[0]["status"] == "done"


def _ts_of(e):
    from datetime import datetime

    return datetime.fromisoformat(e["t"]).timestamp()


def test_search_finds_runs_by_text_level_and_who():
    events = [
        _ev(1, 0, "appscreenmap crawl", "start"),
        _ev(1, 1, "new screen Settings"),
        _ev(1, 2, "exit 0 after 1s", "end", exit=0),
        _ev(2, 3, "appscreenmap security", "start", cmd="security", source="cli"),
        _ev(2, 4, "! cleartext traffic allowed", level="warn", cmd="security", source="cli"),
        _ev(2, 5, "exit 0 after 1s", "end", cmd="security", source="cli", exit=0),
    ]
    no = lambda p: False
    everything = activity.search(events, alive=no)
    assert [s["cmd"] for s in everything["sessions"]] == ["security", "crawl"]  # newest first
    hit = activity.search(events, q="settings", alive=no)["sessions"]
    assert [s["cmd"] for s in hit] == ["crawl"] and hit[0]["snippet"] == "new screen Settings"
    assert [s["cmd"] for s in activity.search(events, level="warn", alive=no)["sessions"]] == ["security"]
    assert activity.search(events, source="agent", alive=no)["total"] == 1
    assert activity.search(events, status="failed", alive=no)["total"] == 0


def test_reader_reads_only_whats_new_and_follows_rotation(tmp_path):
    log = activity.ActivityLog(tmp_path, "crawl", env={}, max_bytes=10_000)
    reader = activity.ActivityReader(tmp_path)
    assert reader.events() == [] and not reader.exists()
    log.line("one")
    log.line("two")
    assert [e["msg"] for e in reader.events()] == ["one", "two"]
    log.line("three")
    assert [e["msg"] for e in reader.events()] == ["one", "two", "three"]
    path = activity.stream_path(tmp_path)
    path.rename(path.with_name(path.name + ".1"))  # rotated: the old lines come from .1, new ones after
    log.line("four")
    assert [e["msg"] for e in reader.events()] == ["one", "two", "three", "four"]
