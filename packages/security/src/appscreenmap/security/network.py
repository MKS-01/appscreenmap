"""Network evidence: run mitmdump with the observation addon, point the device at it, read what it wrote.

mitmproxy is an external tool (`uv tool install mitmproxy`), never a dependency: the addon runs in mitmproxy's own
Python and prints JSON lines, the same way the Frida hook does.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

from appscreenmap.drivers.base import DriverError

ADDON = Path(__file__).parent / "hooks" / "mitm_observe.py"
INSTALL = "uv tool install mitmproxy"
EMULATOR_HOST = "10.0.2.2"  # the Mac's loopback, as an Android emulator sees it
LOG = "network.jsonl"


class CaptureError(RuntimeError):
    pass


def find_mitmdump() -> str | None:
    return shutil.which("mitmdump")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MitmCapture:
    """One mitmdump process writing `out`. Listens on 127.0.0.1 only, so the proxy is never open to the network."""

    def __init__(self, out: Path, mode: str = "observe", secret_names=(), mitmdump: str | None = None):
        self.out, self.mode = Path(out), mode
        self.secret_names = [n for n in secret_names if n]
        self.mitmdump = mitmdump or find_mitmdump()
        self.port = 0
        self.proc: subprocess.Popen | None = None

    def start(self, timeout: float = 20) -> None:
        if not self.mitmdump:
            raise CaptureError(f"mitmproxy is not installed: {INSTALL}")
        self.port = _free_port()
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.touch()
        log = open(self.out.with_name("network-proxy.log"), "w")  # noqa: SIM115 (closed once the process has it)
        env = {**os.environ, "ASM_SECRET_NAMES": ",".join(self.secret_names)}
        self.proc = subprocess.Popen(
            [self.mitmdump, "-q", "-s", str(ADDON), "--listen-host", "127.0.0.1", "--listen-port", str(self.port),
             "--set", f"asm_out={self.out}", "--set", f"asm_mode={self.mode}"],
            stdout=log, stderr=subprocess.STDOUT, env=env,
        )  # fmt: skip
        log.close()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise CaptureError(f"mitmdump exited ({self.proc.returncode}): {self._log_tail()}")
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close()
                return
            except OSError:
                time.sleep(0.2)
        self.stop()
        raise CaptureError(f"mitmdump did not start listening within {timeout:g}s: {self._log_tail()}")

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)

    def _log_tail(self) -> str:
        try:
            return (
                self.out.with_name("network-proxy.log").read_text(errors="replace").strip()[-400:]
                or "no output"
            )
        except OSError:
            return "no output"


@dataclass
class ProxyState:
    port: int
    lost: bool = False


@contextmanager
def proxied(
    driver, capture, on_lost: Callable[[], None] | None = None, poll: float = 1.0
) -> Iterator[ProxyState]:
    """Start `capture`, point the device at it, and always put the device's proxy back.

    That holds on success, on an error, on Ctrl-C, and when the proxy dies mid-crawl (a watchdog restores it at once,
    so the app never loses the network and the crawl never maps error screens).
    """
    before = driver.get_http_proxy()
    if before.startswith(
        EMULATOR_HOST + ":"
    ):  # left behind by a crawl that was killed: not the user's own proxy
        before = ""
    capture.start()
    state = ProxyState(capture.port)
    lock, restored, stop = threading.Lock(), threading.Event(), threading.Event()

    def restore() -> None:
        with lock:
            if not restored.is_set():
                driver.set_http_proxy(before)
                restored.set()

    def watch() -> None:
        while not stop.wait(poll):
            if not capture.alive():
                state.lost = True
                with suppress(DriverError):  # the finally below tries again
                    restore()
                if on_lost:
                    on_lost()
                return

    try:
        driver.set_http_proxy(f"{EMULATOR_HOST}:{capture.port}")
        watcher = threading.Thread(target=watch, name="proxy-watchdog", daemon=True)
        watcher.start()
        yield state
    finally:
        stop.set()
        try:
            restore()
        finally:
            capture.stop()


def read_log(path: Path) -> list[dict]:
    """The addon's rows; other lines (and a missing file) are ignored."""
    rows = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if isinstance(o, dict) and o.get("asm") == 1:
            rows.append(o)
    return rows


def summarize(rows: list[dict]) -> dict:
    """Hosts the app contacted, with how: requests, tunnels (TLS left untouched), plain http://, failures."""
    hosts: dict[str, dict] = {}
    for r in rows:
        host = r.get("host")
        if not host:
            continue
        h = hosts.setdefault(host, {"host": host, "requests": 0, "tunnels": 0, "cleartext": 0, "failed": 0})
        if r["event"] == "connect":
            h["tunnels"] += 1
        elif r["event"] == "connect_failed":
            h["failed"] += 1
        elif r["event"] == "request":
            h["requests"] += 1
            h["cleartext"] += r.get("scheme") == "http"
            h["failed"] += bool(r.get("error"))
    ordered = sorted(hosts.values(), key=lambda h: (-(h["requests"] + h["tunnels"]), h["host"]))
    return {
        "events": len(rows),
        "hosts": ordered,
        "cleartext_hosts": [h["host"] for h in ordered if h["cleartext"]],
    }
