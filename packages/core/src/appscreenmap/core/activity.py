"""The activity log: what every engine command is doing, as it happens, whoever started it.

Each command still prints to the terminal as before. Its output also goes, line by line, to one shared stream,
`runs/.logs/activity.jsonl`: one JSON event per line, for every command and every source (you in a terminal, an AI
agent, the MCP server, CI). Once a command knows its run, the same lines go to that run's `log.txt` too, so the log
travels with the run. `appscreenmap logs` and the terminal home follow the stream live.

An event: {"t", "cmd", "run", "source", "level", "msg", "pid"} plus "kind": "start" | "end" on the first and last
event of a command, and "exit" (the exit code) on the last. The dashboard reads the stream as sessions, one per
command run (`ActivityReader`, `sessions`). Secrets (the values behind `${NAME}` placeholders, the test account's password, and any
environment variable that looks like a password, token or key) are masked in the terminal output, the stream and
the run log. The stream rotates at MAX_BYTES, keeping one older file.
"""

from __future__ import annotations

import io
import json
import os
import re
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

LOGS_DIR = ".logs"
ACTIVITY_FILE = "activity.jsonl"
RUN_LOG = "log.txt"
MAX_BYTES = 5_000_000
MAX_LINES = 2_000  # per command: a `report --json` must not flood the stream
SOURCES = ("agent", "cli", "mcp", "ci")
LEVELS = ("info", "warn", "error")
MASK = "••••"
MIN_SECRET = 4  # shorter values would mask ordinary words
_SECRET_ENV_RE = re.compile(r"PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE_KEY", re.IGNORECASE)
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def stream_path(runs_root: str | Path) -> Path:
    return Path(runs_root) / LOGS_DIR / ACTIVITY_FILE


def detect_source(env=os.environ) -> str:
    """Who started this command: APPSCREENMAP_SOURCE when a launcher sets it, else an AI agent's or CI's own
    environment variables, else a person at a terminal."""
    named = (env.get("APPSCREENMAP_SOURCE") or "").lower()
    if named in SOURCES:
        return named
    if env.get("CLAUDECODE") or env.get("AI_AGENT"):
        return "agent"
    if env.get("CI"):
        return "ci"
    return "cli"


def level_of(line: str, stream: str) -> str:
    s = line.lstrip().lower()
    if s.startswith(("error", "device error", "! error")):
        return "error"
    if stream == "stderr" or s.startswith("!"):
        return "warn"
    return "info"


def env_secrets(env=os.environ) -> list[str]:
    return [v for k, v in env.items() if _SECRET_ENV_RE.search(k) and len(v or "") >= MIN_SECRET]


class ActivityLog:
    """One command's log. `line` and `event` are safe to call from several threads."""

    def __init__(
        self,
        runs_root: str | Path,
        cmd: str,
        source: str | None = None,
        env=os.environ,
        max_bytes: int = MAX_BYTES,
        max_lines: int = MAX_LINES,
    ):
        self.path = stream_path(runs_root)
        self.cmd = cmd
        self.source = source or detect_source(env)
        self.run: str | None = None
        self.max_bytes = max_bytes
        self.max_lines = max_lines
        self.lines = 0
        self.pid = os.getpid()
        self._run_log: Path | None = None
        self._early: list[str] = []  # lines from before the run was known, copied into its log.txt
        self._secrets: tuple[str, ...] = ()  # longest first, so a secret inside another is masked whole
        self._lock = threading.Lock()
        self.add_secrets(env_secrets(env))

    # ── secrets ──────────────────────────────────────────────────────────────
    def add_secrets(self, values: Iterable[str | None]) -> None:
        with self._lock:
            known = set(self._secrets) | {v for v in values if v and len(v) >= MIN_SECRET}
            self._secrets = tuple(sorted(known, key=len, reverse=True))

    def mask(self, text: str) -> str:
        for s in self._secrets:
            if s in text:
                text = text.replace(s, MASK)
        return text

    # ── writing ──────────────────────────────────────────────────────────────
    def bind_run(self, run_dir: str | Path) -> None:
        """From now on, events name this run and its lines also go to <run_dir>/log.txt."""
        run_dir = Path(run_dir)
        with self._lock:
            self.run = run_dir.name
            self._run_log = run_dir / RUN_LOG
            early, self._early = self._early, []
            if early:
                self._append(self._run_log, "".join(early))

    def event(self, msg: str, level: str = "info", kind: str | None = None, code: int | None = None) -> None:
        msg = self.mask(_ANSI_RE.sub("", msg)).rstrip()
        row = {
            "t": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "cmd": self.cmd,
            "run": self.run,
            "source": self.source,
            "level": level if level in LEVELS else "info",
            "msg": msg,
            "pid": self.pid,
        }
        if kind:
            row["kind"] = kind
        if code is not None:
            row["exit"] = code
        text = f"{row['t'][11:19]} {msg}\n"
        with self._lock:
            self._rotate()
            self._append(self.path, json.dumps(row, ensure_ascii=False) + "\n")
            if self._run_log is not None:
                self._append(self._run_log, text)
            else:
                self._early.append(text)

    def line(self, text: str, stream: str = "stdout") -> None:
        """One line a command printed. Blank lines are skipped; past max_lines, one notice and then nothing."""
        if not text.strip():
            return
        self.lines += 1
        if self.lines == self.max_lines + 1:
            self.event(f"… more output not logged (over {self.max_lines} lines)", "warn")
        if self.lines > self.max_lines:
            return
        self.event(text, level_of(text, stream))

    def _rotate(self) -> None:
        try:
            if self.path.stat().st_size >= self.max_bytes:
                os.replace(self.path, self.path.with_name(self.path.name + ".1"))
        except OSError:
            pass

    @staticmethod
    def _append(path: Path, text: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open(
                "a", encoding="utf-8"
            ) as f:  # opened per write: another process may have rotated it
                f.write(text)
        except OSError:
            pass  # logging never breaks a command


class _Tee(io.TextIOBase):
    """A text stream that writes through to the real one (masked) and hands each complete line to the log."""

    def __init__(self, inner, log: ActivityLog, stream: str):
        self.inner, self.log, self.stream = inner, log, stream
        self._buf = ""

    def write(self, s: str) -> int:
        self.inner.write(self.log.mask(s))
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.log.line(
                line.split("\r")[-1], self.stream
            )  # a progress line redrawn with \r: its last state
        return len(s)

    def flush(self) -> None:
        self.inner.flush()

    def drain(self) -> None:
        if self._buf:
            self.log.line(self._buf, self.stream)
            self._buf = ""

    def isatty(self) -> bool:
        return self.inner.isatty()

    def fileno(self) -> int:
        return self.inner.fileno()

    @property
    def encoding(self):
        return getattr(self.inner, "encoding", "utf-8")

    def writable(self) -> bool:
        return True


_current: ActivityLog | None = None


def current() -> ActivityLog | None:
    return _current


def bind_run(run_dir: str | Path) -> None:
    """Name the run the current command is working on (no-op outside a logged command)."""
    if _current is not None:
        _current.bind_run(run_dir)


def add_secrets(values: Iterable[str | None]) -> None:
    if _current is not None:
        _current.add_secrets(values)


@contextmanager
def capture(log: ActivityLog, streams, capture_stdout: bool = True) -> Iterator[ActivityLog]:
    """Tee `streams` (the `sys` module, or anything with stdout/stderr) into `log` for the duration."""
    global _current
    out, err = streams.stdout, streams.stderr
    tees = [_Tee(err, log, "stderr")]
    if capture_stdout:
        tees.append(_Tee(out, log, "stdout"))
        streams.stdout = tees[-1]
    streams.stderr = tees[0]
    _current = log
    try:
        yield log
    finally:
        for t in tees:
            t.drain()
        streams.stdout, streams.stderr = out, err
        _current = None


def read_events(path: str | Path, offset: int = 0) -> tuple[list[dict], int]:
    """Events appended since byte `offset`, and the offset to read from next. A partial last line waits."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        return [], 0
    if size < offset:  # rotated: start the new file from the top
        offset = 0
    with path.open("rb") as f:
        f.seek(offset)
        chunk = f.read()
    end = chunk.rfind(b"\n") + 1
    events = []
    for raw in chunk[:end].splitlines():
        try:
            events.append(json.loads(raw))
        except ValueError:
            continue
    return events, offset + end


# ── reading, for the dashboard ───────────────────────────────────────────────
RECENT_S = 15  # a finished command stays in the live view this long
_EXIT_RE = re.compile(r"exit (-?\d+)\b")


class ActivityReader:
    """The stream (rotated file first, then the current one) as parsed events, re-reading only what was appended."""

    def __init__(self, runs_root: str | Path):
        self.path = stream_path(runs_root)
        self.old = self.path.with_name(self.path.name + ".1")
        self._events: list[dict] = []
        self._offset = 0
        self._old_sig: tuple | None = None
        self._lock = threading.Lock()  # the dashboard server reads from several threads

    def _sig(self) -> tuple | None:
        try:
            st = self.old.stat()
            return (st.st_size, st.st_mtime_ns)
        except OSError:
            return None

    def events(self) -> list[dict]:
        """A snapshot: later appends don't change the list a caller holds."""
        with self._lock:
            return list(self._refresh())

    def _refresh(self) -> list[dict]:
        sig = self._sig()
        try:
            size = self.path.stat().st_size
        except OSError:
            size = 0
        if sig != self._old_sig or size < self._offset:  # rotated since the last read: start over
            self._old_sig, self._offset = sig, 0
            self._events = read_events(self.old)[0] if sig else []
        new, self._offset = read_events(self.path, self._offset)
        self._events.extend(new)
        return self._events

    def exists(self) -> bool:
        return self.path.is_file() or self.old.is_file()


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _ts(t: str) -> float:
    try:
        return datetime.fromisoformat(t).timestamp()
    except (TypeError, ValueError):
        return 0.0


def sessions(events: list[dict], alive=_alive, now: float | None = None) -> list[dict]:
    """One record per command run, oldest first: who ran what on which run, when, how it ended, and its lines.

    status: running (no end yet, process alive) · done (exit 0) · failed (exit ≠ 0) · interrupted (no end, and
    the process is gone: killed, or its start/end rotated away)."""
    out: list[dict] = []
    open_: dict[int, dict] = {}
    for i, e in enumerate(events):
        pid = e.get("pid") or 0
        s = open_.get(pid)
        if e.get("kind") == "start" or s is None:
            s = {
                "id": f"{pid}-{re.sub(r'[^0-9]', '', e.get('t', ''))}",  # URL-safe
                "cmd": e.get("cmd", "?"),
                "source": e.get("source", "cli"),
                "run": e.get("run"),
                "pid": pid,
                "start": e.get("t", ""),
                "end": None,
                "exit": None,
                "command": e.get("msg", "") if e.get("kind") == "start" else "",
                "events": [],
            }
            out.append(s)
            open_[pid] = s
        s["events"].append(i)
        s["run"] = e.get("run") or s["run"]
        if e.get("kind") == "end":
            code = e.get("exit")
            if code is None and (
                m := _EXIT_RE.match(e.get("msg") or "")
            ):  # written before "exit" was a field
                code = int(m.group(1))
            s["end"], s["exit"] = e.get("t"), code
            open_.pop(pid, None)
    now = time.time() if now is None else now
    for s in out:
        rows = [events[i] for i in s["events"]]
        lines = [r for r in rows if not r.get("kind")]
        s["lines"] = len(lines)
        s["warnings"] = sum(r.get("level") == "warn" for r in lines)
        s["errors"] = sum(r.get("level") == "error" for r in lines)
        s["last"] = lines[-1]["msg"] if lines else ""
        s["last_t"] = rows[-1].get("t", "")
        if s["end"] is not None:
            s["status"] = "done" if s["exit"] == 0 else "failed"
        elif alive(s["pid"]):
            s["status"] = "running"
        else:
            s["status"] = "interrupted"
        s["recent"] = s["status"] != "running" and now - _ts(s["last_t"]) <= RECENT_S
    return out


def summary(s: dict) -> dict:
    return {k: v for k, v in s.items() if k != "events"}


def matches(e: dict, q: str = "", level: str = "") -> bool:
    if level and LEVELS.index(e.get("level") if e.get("level") in LEVELS else "info") < LEVELS.index(level):
        return False
    return not q or q.lower() in (e.get("msg") or "").lower()


def search(
    events: list[dict],
    q: str = "",
    source: str = "",
    cmd: str = "",
    run: str = "",
    level: str = "",
    status: str = "",
    limit: int = 100,
    alive=_alive,
) -> dict:
    """Sessions that match, newest first, each with how many of its lines match and the first one."""
    found = []
    for s in reversed(sessions(events, alive)):
        if (source and s["source"] != source) or (cmd and s["cmd"] != cmd) or (run and s["run"] != run):
            continue
        if status and s["status"] != status:
            continue
        rows = [events[i] for i in s["events"] if not events[i].get("kind")]
        hits = [r for r in rows if matches(r, q, level)] if (q or level) else rows
        if (q or level) and not hits and not (q and q.lower() in s["command"].lower()):
            continue
        found.append({**summary(s), "matches": len(hits), "snippet": hits[0]["msg"] if hits else ""})
    return {"sessions": found[:limit], "total": len(found)}
