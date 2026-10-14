"""Serve the maps: `serve` (the web viewer and the notes endpoint) and `mcp` (agents, over stdio)."""

from __future__ import annotations

import functools
import http.server
import os
import sys
import webbrowser
from pathlib import Path

from appscreenmap.core import notes
from appscreenmap.core.runs import resolve_run, update_index


def _web_dist() -> Path | None:
    candidates = [
        os.environ.get("APPSCREENMAP_WEB"),
        Path(__file__).resolve().parents[2] / "web",  # bundled in the wheel: appscreenmap/web
    ]
    candidates += [
        d / "apps" / "viewer" / "dist" for d in Path(__file__).resolve().parents
    ]  # source checkout
    for c in candidates:
        if c and (Path(c) / "index.html").is_file():
            return Path(c)
    return None


class _Handler(http.server.SimpleHTTPRequestHandler):
    runs_root: Path
    web_root: Path

    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith("/runs/"):
            rel = clean[len("/runs/") :]
            # /runs/<run-id>/… → runs/<project>/<run-id>/… (ids are flat; folders are per project)
            head, _, rest = rel.partition("/")
            if (
                head
                and not (self.runs_root / head).exists()
                and (run_dir := resolve_run(self.runs_root, head))
            ):
                rel = run_dir.relative_to(self.runs_root).as_posix() + ("/" + rest if rest else "")
            target = (self.runs_root / rel).resolve()
            if self.runs_root.resolve() not in target.parents and target != self.runs_root.resolve():
                return str(self.runs_root / "__forbidden__")
            return str(target)
        target = (self.web_root / clean.lstrip("/")).resolve()
        if not target.exists() or clean == "/":
            return str(self.web_root / "index.html")  # SPA fallback
        return str(target)

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/runs/index.json":
            update_index(self.runs_root)
        super().do_GET()

    def do_PUT(self):
        """Save viewer notes: PUT /runs/[<project>/]<run-id>/notes.json. The only write the server accepts."""
        parts = self.path.split("?", 1)[0].split("/")
        run_dir = None
        if parts[:2] == ["", "runs"] and parts[-1] == notes.NOTES_FILE and len(parts) in (4, 5):
            run_dir = notes.run_dir_for(self.runs_root, parts[-2])
            if (
                run_dir
                and len(parts) == 5
                and run_dir.relative_to(self.runs_root).parts != (parts[2], parts[3])
            ):
                run_dir = None  # the project folder in the URL must be the run's real one
        if run_dir is None:
            return self.send_error(404)
        # Only same-machine pages may write (guards against DNS rebinding); cross-site PUTs already fail CORS preflight.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ("localhost", "127.0.0.1", "::1", self.server.server_address[0]):
            return self.send_error(403)
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send_error(415)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.send_error(411)
        if not 0 < length <= notes.MAX_BYTES:
            return self.send_error(413 if length else 411)
        try:
            notes.save(run_dir, self.rfile.read(length))
        except notes.NotesError as e:
            return self.send_error(400, str(e))
        self.send_response(204)
        self.end_headers()

    def end_headers(self):
        if self.path.startswith("/runs/") and self.path.split("?")[0].endswith(".json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):  # quiet
        pass


def cmd_serve(args) -> int:
    dist = _web_dist()
    if dist is None:
        print("Web viewer not built. Run: bun install && make viewer", file=sys.stderr)
        return 2
    runs_root = Path(args.runs).resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    update_index(runs_root)
    handler = type("Handler", (_Handler,), {"runs_root": runs_root, "web_root": dist})
    server = http.server.ThreadingHTTPServer(
        (args.host, args.port), functools.partial(handler, directory=str(dist))
    )
    url = f"http://{args.host}:{args.port}/"
    print(f"🗺  AppScreenMap viewer → {url}   (runs: {runs_root})  Ctrl+C to stop")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_mcp(args) -> int:
    try:
        from appscreenmap.engine.mcp_server import MapTools, build_server

        server = build_server(MapTools(args.runs, args.run, args.serial))
    except ImportError:
        print("The MCP server needs the mcp extra: pip install 'appscreenmap-engine[mcp]'", file=sys.stderr)
        return 2
    server.run("stdio")
    return 0


def register(sub) -> None:
    s = sub.add_parser("serve", help="open the web viewer")
    s.add_argument("--runs", default="runs")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-open", action="store_true", help="don't open a browser")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("mcp", help="serve the maps to agents over MCP (stdio)")
    s.add_argument("--runs", default="runs", help="runs directory (default: ./runs)")
    s.add_argument("--run", help="default run id (default: the latest finished run)")
    s.add_argument("--serial", help="device for where_am_i / go_to_screen / crawl")
    s.set_defaults(fn=cmd_mcp)
