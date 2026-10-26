"""The app's own log lines while it runs: `adb logcat --pid`, reattached whenever the app restarts with a new pid.

Lines are masked by the caller's `mask` before they are written: a log line can carry tokens and typed passwords.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

# `logcat -v epoch`: "1792608295.581  1234  1250 I PlaygroundNet: GET … -> failed"
_LINE = re.compile(r"^\s*(\d+\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEFA])\s+(.*?)\s*:\s?(.*)$")
LEVELS = {"V": "verbose", "D": "debug", "I": "info", "W": "warn", "E": "error", "F": "fatal", "A": "fatal"}
MAX_MESSAGE = 2000  # cut after masking: a secret straddling the cut would keep its unmasked start
LOG = "logs.jsonl"


def parse_line(line: str) -> dict | None:
    m = _LINE.match(line)
    if not m:
        return None
    t, pid, _tid, level, tag, msg = m.groups()
    return {"t": float(t), "pid": int(pid), "level": LEVELS[level], "tag": tag, "message": msg}


class LogcatCapture:
    """Follows one package's log in a background thread and appends JSON lines to `out`."""

    def __init__(
        self, driver, package: str, out: Path, mask: Callable[[str], str] = lambda s: s, poll: float = 1.0
    ):
        self.d, self.package, self.out, self.mask, self.poll = driver, package, Path(out), mask, poll
        self.lines = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._since = 0.0
        self._skew = 0.0

    def start(self) -> None:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.touch()
        self._skew = self._clock_skew()
        self._since = time.time() - 1  # logcat -T 1 replays one older line; drop anything before we started
        self._thread = threading.Thread(target=self._supervise, name="logcat", daemon=True)
        self._thread.start()

    def _clock_skew(self) -> float:
        """Seconds to add to a device timestamp to get this machine's time (a restored snapshot can lag by minutes)."""
        try:
            t0 = time.time()
            device = float(self.d.shell("date +%s.%N").strip())
            return (t0 + time.time()) / 2 - device
        except Exception:  # noqa: BLE001 (no clock to ask: trust the device)
            return 0.0

    def stop(self) -> None:
        self._stop.set()
        self._kill()
        if self._thread:
            self._thread.join(5)

    def _kill(self) -> None:
        p, self._proc = self._proc, None
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(3)
            except subprocess.TimeoutExpired:
                p.kill()

    def _supervise(self) -> None:
        pid = None
        while not self._stop.is_set():
            try:
                now = self.d.pidof(self.package)
            except Exception:  # noqa: BLE001 (adb hiccup: try again on the next poll)
                now = pid
            if now != pid or (now and (self._proc is None or self._proc.poll() is not None)):
                self._kill()
                pid = now
                if pid:
                    self._proc = self.d.logcat_popen(pid)
                    threading.Thread(target=self._read, args=(self._proc,), daemon=True).start()
            self._stop.wait(self.poll)

    def _read(self, proc: subprocess.Popen) -> None:
        for raw in proc.stdout:
            row = parse_line(raw.decode(errors="replace") if isinstance(raw, bytes) else raw)
            if not row:
                continue
            row["t"] += self._skew  # device clock → this machine's, which the timeline and the proxy rows use
            if row["t"] < self._since:
                continue
            row["message"] = self.mask(row["message"])[:MAX_MESSAGE]
            row["tag"] = self.mask(row["tag"])
            with self._lock, self.out.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps({"asm": 1, "event": "log", "source": "logcat", **row}, ensure_ascii=False)
                    + "\n"
                )
                self.lines += 1
