"""Every command an agent or a person runs is in the activity log; `logs` shows it, filtered."""

from __future__ import annotations

import json
from argparse import Namespace

from appscreenmap.core import activity
from appscreenmap.engine.cli import logs, main
from appscreenmap.testkit.fakedevice import FakeDriver, crawl


def _events(root):
    return [json.loads(line) for line in activity.stream_path(root).read_text().splitlines()]


def test_a_command_logs_start_output_and_end_tagged_with_its_run(tmp_path, monkeypatch):
    monkeypatch.setenv("APPSCREENMAP_SOURCE", "agent")
    run, _ = crawl(tmp_path, FakeDriver(), run_id="proj-20261016-120000")
    (tmp_path / "index.json").write_text('{"runs": []}')
    assert main(["report", str(run)]) == 0
    ev = _events(tmp_path)
    assert ev[0]["kind"] == "start" and ev[0]["msg"].startswith("appscreenmap report")
    assert ev[-1]["kind"] == "end" and ev[-1]["msg"].startswith("exit 0")
    assert len(ev) > 2 and {e["run"] for e in ev} == {run.name}
    assert {e["source"] for e in ev} == {"agent"} and {e["cmd"] for e in ev} == {"report"}
    assert "exit 0" in (run / activity.RUN_LOG).read_text()


def test_json_output_is_not_copied_into_the_stream(tmp_path):
    run, _ = crawl(tmp_path, FakeDriver(), run_id="proj-20261016-120000")
    (tmp_path / "index.json").write_text('{"runs": []}')
    assert main(["report", str(run), "--json"]) == 0
    assert [e.get("kind") for e in _events(tmp_path)] == ["start", "end"]


def test_no_runs_folder_means_no_log_is_made(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["store", "--apk", str(tmp_path / "missing.apk")])
    assert not (tmp_path / "runs").exists()


def test_merge_keeps_the_runs_logs_in_the_canvas(tmp_path):
    canvas, _ = crawl(tmp_path, FakeDriver(), run_id="canvas")
    rerun, _ = crawl(tmp_path, FakeDriver(), run_id="proj-20261016-120000")
    (canvas / activity.RUN_LOG).write_text("first crawl\n")
    (rerun / activity.RUN_LOG).write_text("second crawl\n")
    args = ["merge", "--into", str(canvas), str(rerun), "--move", "--out", str(tmp_path)]
    assert main(args) == 0
    text = (canvas / activity.RUN_LOG).read_text()
    assert text.index("first crawl") < text.index("second crawl") < text.index("added to")


def _args(**kw):
    base = {"run": None, "filter_cmd": None, "source": None, "level": None}
    return Namespace(**{**base, **kw})


def test_filters():
    e = {"run": "r1", "cmd": "crawl", "source": "agent", "level": "warn"}
    assert logs.matches(e, _args())
    assert logs.matches(e, _args(source="agent", filter_cmd="crawl", run="r1", level="warn"))
    assert not logs.matches(e, _args(source="cli"))
    assert not logs.matches(e, _args(level="error"))
    assert logs.matches({**e, "level": "nonsense"}, _args(level="info"))


def test_logs_prints_the_last_events(tmp_path, capsys):
    log = activity.ActivityLog(tmp_path, "security", source="agent", env={})
    for i in range(5):
        log.line(f"finding {i}")
    assert main(["logs", "--runs", str(tmp_path), "--no-follow", "-n", "2"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2 and out[-1].endswith("[agent] security · finding 4")
    assert len(_events(tmp_path)) == 5  # reading the log does not log itself
