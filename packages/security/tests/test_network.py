"""Network capture: the mitmproxy addon's rows, the device proxy always put back, and a live mitmdump round trip."""

from __future__ import annotations

import http.client
import importlib.util
import json
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from appscreenmap.security import network
from appscreenmap.testkit.fakedevice import FakeDriver


def _addon_module():
    spec = importlib.util.spec_from_file_location("mitm_observe", network.ADDON)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _flow(
    method="GET", scheme="https", host="api.playground.test", port=443, path="/v1/me", status=200, error=None
):
    req = SimpleNamespace(
        method=method, scheme=scheme, host=host, port=port, path=path, timestamp_start=1000.0,
        raw_content=b"", http_version="HTTP/1.1",
    )  # fmt: skip
    resp = None
    if status is not None:
        resp = SimpleNamespace(
            status_code=status, timestamp_end=1000.25, raw_content=b"x" * 12,
            headers={"content-type": "application/json; charset=utf-8"},
        )  # fmt: skip
    return SimpleNamespace(
        request=req, response=resp, error=error, metadata={}, server_conn=SimpleNamespace(error=None)
    )


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def addon(tmp_path):
    a = _addon_module().Observe()
    out = tmp_path / "network.jsonl"
    a.setup(str(out), "observe", env={"ASM_SECRET_NAMES": "APP_PASSWORD", "APP_PASSWORD": "hunter22"})
    yield a, out
    a.done()


def test_request_row_keeps_metadata_only(addon):
    a, out = addon
    a.response(_flow(path="/v1/me?token=abc123&fields=name&fields=email"))
    (row,) = _rows(out)
    assert row["event"] == "request" and row["source"] == "proxy" and row["mode"] == "observe"
    assert row["path"] == "/v1/me"
    assert row["query_keys"] == ["fields", "token"]
    assert "abc123" not in out.read_text()  # query values never stored
    assert row["status"] == 200 and row["content_type"] == "application/json"
    assert row["t"] == 1000.0 and row["t_end"] == 1000.25 and row["bytes_in"] == 12


def test_typed_secrets_are_masked_wherever_they_appear(addon):
    a, out = addon
    a.response(_flow(scheme="http", port=80, path="/login/hunter22/ok"))
    a.error(_flow(path="/x", status=None, error="cannot reach hunter22.playground.test"))
    text = out.read_text()
    assert "hunter22" not in text
    assert "/login/••••/ok" in text


def test_one_row_per_flow_and_connect_errors_are_their_own_event(addon):
    a, out = addon
    f = _flow()
    a.response(f)
    a.error(f)  # mitmproxy can report an error after the response (client went away)
    a.error(_flow(method="CONNECT", status=None, error="x"))  # CONNECT flows are logged by http_connect*
    connect = _flow(method="CONNECT", status=None)
    a.http_connect(connect)
    connect.server_conn.error = "[Errno 8] nodename nor servname provided"
    a.http_connect_error(connect)
    events = [r["event"] for r in _rows(out)]
    assert events == ["request", "connect", "connect_failed"]
    assert _rows(out)[2]["error"].startswith("[Errno 8]")


def test_observe_passes_tls_through_and_decrypt_does_not(tmp_path):
    a = _addon_module().Observe()
    a.setup("", "observe", env={})
    hello = SimpleNamespace(ignore_connection=False)
    a.tls_clienthello(hello)
    assert hello.ignore_connection is True
    a.setup("", "decrypt", env={})
    hello = SimpleNamespace(ignore_connection=False)
    a.tls_clienthello(hello)
    assert hello.ignore_connection is False
    a.response(_flow())  # no output file: nothing written, no error


def test_summarize_counts_hosts_tunnels_and_cleartext():
    rows = [
        {"asm": 1, "event": "connect", "host": "api.playground.test"},
        {"asm": 1, "event": "connect_failed", "host": "api.playground.test"},
        {"asm": 1, "event": "request", "host": "cdn.playground.test", "scheme": "http", "error": "offline"},
        {"asm": 1, "event": "connect", "host": "events.tracker.test"},
    ]
    s = network.summarize(rows)
    assert [h["host"] for h in s["hosts"]] == [
        "api.playground.test",
        "cdn.playground.test",
        "events.tracker.test",
    ]
    assert s["cleartext_hosts"] == ["cdn.playground.test"]
    assert s["hosts"][0] == {
        "host": "api.playground.test",
        "requests": 0,
        "tunnels": 1,
        "cleartext": 0,
        "failed": 1,
    }


def test_read_log_ignores_other_lines(tmp_path):
    p = tmp_path / "network.jsonl"
    p.write_text('{"asm": 1, "event": "connect", "host": "a"}\nnot json\n{"other": 1}\n')
    assert len(network.read_log(p)) == 1
    assert network.read_log(tmp_path / "missing.jsonl") == []


# ── the device proxy is always put back ─────────────────────────────────────


class FakeCapture:
    def __init__(self, port=8123):
        self.port, self.running, self.stopped = port, False, False

    def start(self):
        self.running = True

    def alive(self):
        return self.running

    def stop(self):
        self.running, self.stopped = False, True


def test_proxy_set_during_and_cleared_after_a_normal_crawl():
    d, cap = FakeDriver(), FakeCapture()
    with network.proxied(d, cap) as state:
        assert d.http_proxy == "10.0.2.2:8123"
        assert state.port == 8123
    assert d.http_proxy == "" and cap.stopped


@pytest.mark.parametrize("exc", [KeyboardInterrupt, RuntimeError])
def test_proxy_cleared_on_ctrl_c_and_on_a_crash(exc):
    d, cap = FakeDriver(), FakeCapture()
    with pytest.raises(exc), network.proxied(d, cap):
        raise exc()
    assert d.http_proxy == "" and cap.stopped


def test_watchdog_clears_the_proxy_when_mitmdump_dies():
    d, cap, lost = FakeDriver(), FakeCapture(), []
    with network.proxied(d, cap, on_lost=lambda: lost.append(d.http_proxy), poll=0.01) as state:
        cap.running = False  # mitmdump killed mid-crawl
        deadline = time.monotonic() + 2
        while not lost and time.monotonic() < deadline:
            time.sleep(0.01)
        assert lost == [""], "the device was left pointing at a dead proxy"
        assert state.lost
    assert d.http_proxy == ""


def test_users_own_proxy_is_restored_but_a_leftover_one_is_not():
    d = FakeDriver()
    d.http_proxy = "proxy.corp.test:3128"
    with network.proxied(d, FakeCapture()):
        pass
    assert d.http_proxy == "proxy.corp.test:3128"
    d.http_proxy = "10.0.2.2:9999"  # left behind by a crawl that was killed
    with network.proxied(d, FakeCapture()):
        pass
    assert d.http_proxy == ""


def test_proxy_untouched_when_the_capture_cannot_start():
    class Broken(FakeCapture):
        def start(self):
            raise network.CaptureError("mitmdump exited (1)")

    d = FakeDriver()
    with pytest.raises(network.CaptureError), network.proxied(d, Broken()):
        pass
    assert d.http_proxy == ""


# ── live: a real mitmdump with the addon (skipped without mitmproxy) ────────


@pytest.mark.skipif(not network.find_mitmdump(), reason=f"mitmproxy not installed ({network.INSTALL})")
def test_live_mitmdump_records_offline_hosts_without_touching_tls(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "hunter22")
    out = tmp_path / "network.jsonl"
    cap = network.MitmCapture(out, "observe", ["APP_PASSWORD"])
    cap.start()
    try:
        proxy = urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{cap.port}"})
        with pytest.raises(urllib.error.HTTPError):  # .test never resolves: the proxy answers 502
            urllib.request.build_opener(proxy).open("http://cdn.playground.test/a.png?u=hunter22", timeout=10)
        conn = http.client.HTTPSConnection("127.0.0.1", cap.port, timeout=10)
        conn.set_tunnel("api.playground.test", 443)
        with pytest.raises(OSError):
            conn.connect()
    finally:
        cap.stop()
    rows = network.read_log(out)
    assert {(r["event"], r["host"]) for r in rows} >= {
        ("request", "cdn.playground.test"),
        ("connect", "api.playground.test"),
    }
    assert "hunter22" not in out.read_text()
    assert network.summarize(rows)["cleartext_hosts"] == ["cdn.playground.test"]


def test_request_rows_split_their_time_into_phases(addon):
    a, out = addon
    f = _flow(scheme="http", port=80)
    f.request.timestamp_end = 1000.002
    f.server_conn = SimpleNamespace(error=None, timestamp_start=1000.003, timestamp_tcp_setup=1000.023)
    f.response.timestamp_start = 1000.203
    a.response(f)
    reused = _flow(scheme="http", port=80)
    reused.request.timestamp_end = 1000.002
    reused.server_conn = SimpleNamespace(error=None, timestamp_start=900.0, timestamp_tcp_setup=900.02)
    reused.response.timestamp_start = 1000.102
    a.response(reused)
    new, old = _rows(out)
    assert new["timing"] == {
        "connect": 20,
        "send": 2,
        "wait": 180,
        "receive": 47,
    }  # waited from the connection
    assert old["timing"] == {
        "send": 2,
        "wait": 100,
        "receive": 148,
    }  # a reused connection has no connect phase
    a.error(_flow(path="/x", status=None, error="boom"))
    assert "timing" not in _rows(out)[2]  # the fake flow has no timestamps beyond the start
