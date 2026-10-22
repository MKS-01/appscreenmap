"""mitmproxy addon: one JSON line per connection or request the app makes, metadata only.

Loaded by `mitmdump -s` (see `appscreenmap.security.network`). Standard library only: it runs in mitmproxy's own
Python, so it can't import appscreenmap. Only `configure` touches mitmproxy (to read its options), so tests drive the
hooks with plain objects.
"""

from __future__ import annotations

import json
import os
from urllib.parse import parse_qsl

MASK = "••••"  # same mask and minimum length as appscreenmap.core.activity
MIN_SECRET = 4


class Observe:
    def __init__(self) -> None:
        self.out = None
        self.mode = "observe"
        self.secrets: tuple[str, ...] = ()

    def load(self, loader) -> None:
        loader.add_option("asm_out", str, "", "File to append AppScreenMap's JSON lines to.")
        loader.add_option("asm_mode", str, "observe", "observe: TLS passes through untouched | decrypt")

    def configure(self, updated) -> None:
        from mitmproxy import ctx  # only inside mitmdump; tests call setup() instead

        self.setup(ctx.options.asm_out, ctx.options.asm_mode)

    def setup(self, out: str, mode: str = "observe", env=os.environ) -> None:
        if self.out:
            self.out.close()
        self.out = open(out, "a", encoding="utf-8", buffering=1) if out else None  # noqa: SIM115 (open until done)
        self.mode = mode
        # The crawler types these values; none may reach the file, wherever the app puts them.
        names = [n for n in env.get("ASM_SECRET_NAMES", "").split(",") if n]
        values = {env.get(n, "") for n in names}
        self.secrets = tuple(sorted((v for v in values if len(v) >= MIN_SECRET), key=len, reverse=True))

    def done(self) -> None:
        if self.out:
            self.out.close()
            self.out = None

    # ── hooks ────────────────────────────────────────────────────────────
    def tls_clienthello(self, data) -> None:
        # observe: the app talks to its real servers through an untouched tunnel, so it behaves as users see it.
        if self.mode == "observe":
            data.ignore_connection = True

    def http_connect(self, flow) -> None:
        self._write("connect", flow.request.timestamp_start, host=flow.request.host, port=flow.request.port)

    def http_connect_error(self, flow) -> None:
        err = getattr(flow.server_conn, "error", None) or flow.error
        self._write(
            "connect_failed",
            flow.request.timestamp_start,
            host=flow.request.host,
            port=flow.request.port,
            error=err,
        )

    def response(self, flow) -> None:
        self._request(flow)

    def error(self, flow) -> None:
        if flow.request.method != "CONNECT":
            self._request(flow)

    # ── rows ─────────────────────────────────────────────────────────────
    def _request(self, flow) -> None:
        if flow.metadata.get("asm_logged"):
            return
        flow.metadata["asm_logged"] = True
        req, resp = flow.request, flow.response
        path, _, query = req.path.partition("?")
        keys = sorted({k for k, _ in parse_qsl(query, keep_blank_values=True)})
        self._write(
            "request",
            req.timestamp_start,
            t_end=resp.timestamp_end if resp and resp.timestamp_end else None,
            method=req.method,
            scheme=req.scheme,
            host=req.host,
            port=req.port,
            path=path,
            query_keys=keys,
            status=resp.status_code if resp else None,
            content_type=(resp.headers.get("content-type", "").split(";")[0].strip() or None)
            if resp
            else None,
            bytes_out=len(req.raw_content or b""),
            bytes_in=len(resp.raw_content or b"") if resp else 0,
            http_version=req.http_version,
            timing=_timing(flow),
            error=flow.error,
        )

    def _write(self, event: str, t, **fields) -> None:
        if not self.out:
            return
        row = {
            "asm": 1,
            "event": event,
            "source": "proxy",
            "mode": self.mode,
            "t": round(t, 3) if t else None,
        }
        for k, v in fields.items():
            if v is None:
                continue
            if k == "error":
                v = str(v)[:160]
            if k == "t_end":
                v = round(v, 3)
            row[k] = self._mask(v)
        self.out.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _mask(self, v):
        if isinstance(v, str):
            for s in self.secrets:
                v = v.replace(s, MASK)
        elif isinstance(v, list):
            v = [self._mask(x) for x in v]
        return v


def _ms(a, b) -> int | None:
    return round((b - a) * 1000) if a and b and b >= a else None


def _timing(flow) -> dict | None:
    """Where a request's time went, in ms, as the proxy saw it (between the proxy and the server).

    connect and tls only when this request opened the connection; a reused one has neither. No DNS phase: mitmproxy
    resolves inside connect.
    """
    req, resp, conn = flow.request, flow.response, flow.server_conn
    opened = getattr(conn, "timestamp_start", None)
    tcp = getattr(conn, "timestamp_tcp_setup", None)
    tls = getattr(conn, "timestamp_tls_setup", None)
    sent = getattr(req, "timestamp_end", None)
    new = bool(opened and req.timestamp_start and opened >= req.timestamp_start)
    first_byte = getattr(resp, "timestamp_start", None) if resp else None
    phases = {
        "connect": _ms(opened, tcp) if new else None,
        "tls": _ms(tcp, tls) if new else None,
        "send": _ms(req.timestamp_start, sent),
        "wait": _ms(
            max(x for x in (sent, tcp if new else None, tls if new else None) if x) if sent else None,
            first_byte,
        ),
        "receive": _ms(first_byte, getattr(resp, "timestamp_end", None) if resp else None),
    }
    phases = {k: v for k, v in phases.items() if v is not None}
    return phases or None


addons = [Observe()]
