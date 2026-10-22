"""App log capture: logcat lines parsed, masked, and followed across app restarts (new pid)."""

from __future__ import annotations

import json
import subprocess
import sys
import time

from appscreenmap.drivers.logcat import LogcatCapture, parse_line


def test_parse_epoch_line():
    row = parse_line(
        "1792608295.581  4321  4350 I PlaygroundNet: GET https://api.playground.test/v1/status -> failed"
    )
    assert row == {
        "t": 1792608295.581,
        "pid": 4321,
        "level": "info",
        "tag": "PlaygroundNet",
        "message": "GET https://api.playground.test/v1/status -> failed",
    }
    assert parse_line("--------- beginning of main") is None


class LogDevice:
    """pidof() follows `pids` (one per poll); each logcat process prints `lines[pid]` with the current time."""

    def __init__(self, pids, lines):
        self.pids, self.lines = list(pids), lines

    def pidof(self, pkg):
        return self.pids.pop(0) if len(self.pids) > 1 else self.pids[0]

    def logcat_popen(self, pid):
        old = f"{time.time() - 60:.3f}  {pid}  {pid} I Old: from before the capture started"
        now = [f"{time.time():.3f}  {pid}  {pid} {msg}" for msg in self.lines.get(pid, [])]
        script = (
            "import sys,time\n" + "".join(f"print({line!r})\n" for line in [old, *now]) + "time.sleep(30)\n"
        )
        return subprocess.Popen([sys.executable, "-u", "-c", script], stdout=subprocess.PIPE)


def test_follows_the_app_across_a_restart_and_masks_lines(tmp_path):
    dev = LogDevice(
        [None, 100, 100, 200],
        {100: ["I Auth: token for hunter22 ok"], 200: ["E Cart: parse failed"]},
    )
    out = tmp_path / "logs.jsonl"
    cap = LogcatCapture(dev, "dev.example", out, mask=lambda s: s.replace("hunter22", "••••"), poll=0.05)
    cap.start()
    deadline = time.monotonic() + 5
    while cap.lines < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    cap.stop()
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert [(r["pid"], r["tag"], r["level"]) for r in rows] == [(100, "Auth", "info"), (200, "Cart", "error")]
    assert rows[0]["message"] == "token for •••• ok" and rows[0]["source"] == "logcat"
    assert "Old" not in out.read_text()  # lines from before the capture are dropped
