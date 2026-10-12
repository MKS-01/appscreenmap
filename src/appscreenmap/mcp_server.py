"""`appscreenmap mcp`: the map as an MCP server, so agents ask it instead of exploring again.

Map tools (no device): list_runs, list_screens, find_screens, get_screen, screenshot, route,
a11y_findings, perf_summary. Device tools: where_am_i (match the live screen to the map),
go_to_screen (drive the device there), crawl / crawl_status (map an app in the background).

The tool logic lives in `MapTools` (plain Python, unit tested); `build_server` registers it with the
MCP SDK (`pip install 'appscreenmap[mcp]'`).
"""

from __future__ import annotations

import functools
import heapq
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from .a11y import audit_run
from .model import load_map
from .perf import summarize as summarize_perf
from .runs import resolve_run, update_index
from .verify import required_secrets

INSTRUCTIONS = """\
AppScreenMap has crawled mobile apps and recorded every screen, element and transition. Use it as
memory of the app instead of exploring again:
- "how do I reach X?" → find_screens("X"), then route(to=...) for the steps (or go_to_screen to do them)
- "where am I?" → where_am_i (matches the live device screen to the map)
- "which screens fail WCAG?" → a11y_findings; "which screens are slow?" → perf_summary
Screen ids (s001, s002, …) belong to one run; most tools default to the latest run.
"""
LEVELS = {"A": 1, "AA": 2, "AAA": 3}
_RUN_DIR_RE = re.compile(r"mapping .* → (\S+)\s*$", re.MULTILINE)  # the crawl's first line


def _selector(el: dict) -> dict:
    """The selector a map element would get from model.selector_for."""
    sel: dict = {}
    if el.get("rid"):
        sel["id"] = el["rid"]
    if (el.get("text") or "").strip():
        sel["text"] = el["text"].strip()
    elif (el.get("desc") or "").strip():
        sel["desc"] = el["desc"].strip()
    x1, y1, x2, y2 = el.get("bounds") or (0, 0, 0, 0)
    sel["point"] = [(x1 + x2) // 2, (y1 + y2) // 2]
    return sel


def shortest_path(data: dict, src: str, dst: str) -> list[dict] | None:
    """Fewest recorded transitions from one screen to another (back/up edges cost more: where they
    lead depends on history). None when the map has no way there."""
    screens = {s["id"]: s for s in data["screens"]}
    out: dict[str, list[dict]] = {}
    for t in data["transitions"]:
        if screens.get(t["to"], {}).get("kind") == "app" and t["action"] != "scroll":
            out.setdefault(t["from"], []).append(t)
    dist, prev, heap = {src: 0.0}, {}, [(0.0, src)]
    while heap:
        d, sid = heapq.heappop(heap)
        if sid == dst:
            break
        if d > dist.get(sid, float("inf")):
            continue
        for t in out.get(sid, []):
            cost = d + (3.0 if t["kind"] in ("back", "up") else 1.0) + (0.5 if t.get("inferred") else 0.0)
            if cost < dist.get(t["to"], float("inf")):
                dist[t["to"]], prev[t["to"]] = cost, t
                heapq.heappush(heap, (cost, t["to"]))
    if dst not in dist:
        return None
    path, cur = [], dst
    while cur in prev:
        path.append(prev[cur])
        cur = prev[cur]["from"]
    return path[::-1]


def transition_steps(data: dict, transitions: list[dict]) -> list[dict]:
    """Recorded transitions as replayable steps (the reach_path format)."""
    screens = {s["id"]: s for s in data["screens"]}
    steps = []
    for t in transitions:
        el = next((e for e in screens[t["from"]].get("elements", []) if e["key"] == t["key"]), {})
        steps.append(
            {
                "screen": t["from"],
                "key": t["key"],
                "action": t["action"],
                "label": t["label"],
                "selector": _selector(el) if el else {},
                "scroll_depth": el.get("scroll_depth", 0),
                "to": t["to"],
            }
        )
    return steps


def describe_step(step: dict, screens: dict) -> str:
    title = screens.get(step["screen"], {}).get("title") or step["screen"]
    if step["action"] == "back":
        return f"on {step['screen']} '{title}': press Back"
    verb = "long-press" if step["action"] == "long_click" else "tap"
    sel = step.get("selector", {})
    where = f" (id {sel['id']})" if sel.get("id") else ""
    if step.get("scroll_depth"):
        where += ", scroll down to find it"
    return f"on {step['screen']} '{title}': {verb} '{step['label']}'{where}"


class MapTools:
    def __init__(self, runs_root: str | Path = "runs", run: str | None = None, serial: str | None = None):
        self.runs_root = Path(runs_root).resolve()
        self.default_run = run
        self.serial = serial
        self._cache: dict[Path, tuple[float, dict]] = {}
        self._jobs: dict[str, dict] = {}

    # ── runs ─────────────────────────────────────────────────────────────────
    def _run_dir(self, run: str | None) -> Path:
        run = run or self.default_run
        if run:
            p = Path(run)
            if (p / "map.json").is_file():
                return p
            if (d := resolve_run(self.runs_root, run)) is not None:
                return d
            raise ValueError(f"no run {run!r} under {self.runs_root}; see list_runs")
        rows = update_index(self.runs_root)
        if not rows:
            raise ValueError(f"no runs under {self.runs_root}; crawl an app first")
        best = next((r for r in rows if r["status"] == "done"), rows[0])
        return self.runs_root / best["path"]

    def _data(self, run: str | None) -> tuple[Path, dict]:
        d = self._run_dir(run)
        mtime = (d / "map.json").stat().st_mtime
        cached = self._cache.get(d)
        if cached is None or cached[0] != mtime:
            cached = (mtime, load_map(d))
            self._cache[d] = cached
        return d, cached[1]

    def _screen(self, data: dict, screen: str) -> dict:
        s = next((s for s in data["screens"] if s["id"] == screen), None)
        if s is not None:
            return s
        hits = self._search(data, screen)
        if hits:
            return next(s for s in data["screens"] if s["id"] == hits[0]["id"])
        raise ValueError(f"no screen {screen!r} in run {data['run']['id']}; see list_screens")

    def list_runs(self, project: str | None = None) -> dict:
        """Crawled runs, newest first, optionally for one project (app)."""
        rows = update_index(self.runs_root)
        return {
            "runs": [
                {
                    "id": r["id"],
                    "project": r["project"],
                    "status": r["status"],
                    "app": f"{r['app'].get('label') or r['app'].get('package')} {r['app'].get('version') or ''}".strip(),
                    "package": r["app"].get("package"),
                    "started_at": r["started_at"],
                    "screens": r["screens"],
                    "transitions": r["transitions"],
                }
                for r in rows
                if not project or r["project"] == project
            ]
        }

    def list_screens(self, run: str | None = None) -> dict:
        """Every screen of a run: id, title, activity, UI patterns, depth from launch."""
        _, data = self._data(run)
        return {
            "run": data["run"]["id"],
            "app": data["run"]["app"].get("package"),
            "stats": {k: data["stats"].get(k) for k in ("screens", "transitions", "crashes", "max_depth")},
            "screens": [
                {
                    "id": s["id"],
                    "title": s.get("title"),
                    "activity": (s.get("activity") or "").rsplit(".", 1)[-1] or None,
                    "patterns": s.get("patterns", []),
                    "depth": s.get("depth"),
                    "variant_of": s.get("variant_of"),
                    "reachable": bool(s.get("reach_path")) or s.get("origin") == "launch",
                }
                for s in data["screens"]
                if s["kind"] == "app"
            ],
        }

    def _search(self, data: dict, query: str) -> list[dict]:
        q = query.strip().lower()
        hits = []
        for s in data["screens"]:
            if s["kind"] != "app":
                continue
            title = (s.get("title") or "").lower()
            labels = [e.get("label") or "" for e in s.get("elements", [])]
            score, why = 0, ""
            if s["id"].lower() == q:
                score, why = 100, "id"
            elif title == q:
                score, why = 90, "title"
            elif q in title:
                score, why = 70, "title"
            elif q in (s.get("activity") or "").lower():
                score, why = 40, "activity"
            elif m := next((lb for lb in labels if q in lb.lower()), None):
                score, why = 30, f"element '{m}'"
            if score:
                # Prefer the shallower screen and the base of a variant group.
                hits.append((score - 0.1 * (s.get("depth") or 0) - (5 if s.get("variant_of") else 0), s, why))
        hits.sort(key=lambda h: -h[0])
        return [{"id": s["id"], "title": s.get("title"), "matched": why} for _, s, why in hits]

    def find_screens(self, query: str, run: str | None = None) -> dict:
        """Screens whose id, title, activity or element labels match a query (e.g. 'settings',
        'Connect Notion', 'Save'), best first."""
        _, data = self._data(run)
        return {"run": data["run"]["id"], "query": query, "screens": self._search(data, query)[:10]}

    def get_screen(self, screen: str, run: str | None = None) -> dict:
        """One screen in full: elements (with where each one leads), how to reach it, transitions in
        and out, accessibility findings and load time. `screen` is an id or a title/label query."""
        d, data = self._data(run)
        s = self._screen(data, screen)
        screens = {x["id"]: x for x in data["screens"]}
        a11y = self._a11y(d)
        perf = self._perf(d)
        flow = d / "flows" / f"{s['id']}.yaml"
        return {
            "run": data["run"]["id"],
            "id": s["id"],
            "title": s.get("title"),
            "activity": s.get("activity"),
            "patterns": s.get("patterns", []),
            "depth": s.get("depth"),
            "variant_of": s.get("variant_of"),
            "size": [s.get("width"), s.get("height")],
            "how_to_reach": [describe_step(st, screens) for st in s.get("reach_path", [])]
            or (["it is the launch screen"] if s.get("origin") == "launch" else ["no recorded path"]),
            "elements": [
                {
                    k: e.get(k)
                    for k in (
                        "key",
                        "kind",
                        "action",
                        "label",
                        "rid",
                        "bounds",
                        "status",
                        "effect",
                        "target",
                        "note",
                    )
                    if e.get(k) not in (None, "")
                }
                for e in s.get("elements", [])
                if e["kind"] != "back"
            ],
            "autofill": [{"label": f["label"], "value": f["value"]} for f in s.get("autofill", [])],
            "leads_to": [
                {
                    "label": t["label"],
                    "to": t["to"],
                    "title": screens[t["to"]].get("title"),
                    "inferred": t["inferred"],
                }
                for t in data["transitions"]
                if t["from"] == s["id"]
            ],
            "reached_from": [
                {"from": t["from"], "label": t["label"]} for t in data["transitions"] if t["to"] == s["id"]
            ],
            "a11y_issues": [_issue(i) for i in a11y["issues"] if i["screen"] == s["id"]],
            "perf": next((p for p in perf["screens"] if p["screen"] == s["id"]), None),
            "files": {
                "screenshot": str(d / s["screenshot"]) if s.get("screenshot") else None,
                "hierarchy": str(d / s["hierarchy"]) if s.get("hierarchy") else None,
                "maestro_flow": str(flow) if flow.is_file() else None,
            },
        }

    def screenshot_path(self, screen: str, run: str | None = None, full: bool = False) -> Path:
        d, data = self._data(run)
        s = self._screen(data, screen)
        rel = s.get("screenshot") if full else (s.get("thumb") or s.get("screenshot"))
        if not rel or not (d / rel).is_file():
            raise ValueError(f"{s['id']} has no screenshot")
        return d / rel

    def route(self, to: str, from_screen: str | None = None, run: str | None = None) -> dict:
        """Steps to reach a screen: from launch (the recorded path, also a Maestro flow), or from
        another screen over recorded transitions. `to`/`from_screen` are ids or title queries."""
        d, data = self._data(run)
        target = self._screen(data, to)
        screens = {s["id"]: s for s in data["screens"]}
        if from_screen:
            src = self._screen(data, from_screen)
            path = shortest_path(data, src["id"], target["id"])
            if path is None:
                raise ValueError(f"the map has no recorded way from {src['id']} to {target['id']}")
            steps = transition_steps(data, path)
            start = src["id"]
        else:
            if not target.get("reach_path") and target.get("origin") != "launch":
                raise ValueError(f"{target['id']} has no recorded path from launch")
            steps = [{**st, "to": nxt} for st, nxt in _with_next(target["reach_path"], target["id"])]
            start = "launch"
        for st in steps:
            st["fill_first"] = [
                {"label": f["label"], "value": f["value"]} for f in screens[st["screen"]].get("autofill", [])
            ]
        flow = d / "flows" / f"{target['id']}.yaml"
        return {
            "run": data["run"]["id"],
            "from": start,
            "to": target["id"],
            "title": target.get("title"),
            "instructions": [describe_step(st, screens) for st in steps],
            "steps": steps,
            "maestro_flow": str(flow) if not from_screen and flow.is_file() else None,
            "env": required_secrets({"screens": [screens[st["screen"]] for st in steps]}),
        }

    # ── reports ──────────────────────────────────────────────────────────────
    def _a11y(self, d: Path) -> dict:
        f = d / "a11y.json"
        if f.is_file():
            return json.loads(f.read_text())
        return audit_run(d, write=False)

    def _perf(self, d: Path) -> dict:
        f = d / "perf.json"
        if f.is_file():
            return json.loads(f.read_text())
        return summarize_perf(d, write=False)

    def a11y_findings(
        self,
        run: str | None = None,
        screen: str | None = None,
        level: str = "AA",
        include_triaged: bool = False,
    ) -> dict:
        """WCAG 2.2 findings from the crawl: which screens fail which success criteria, worst first.
        `level` is the highest conformance level to include (A, AA or AAA)."""
        d, data = self._data(run)
        rep = self._a11y(d)
        sid = self._screen(data, screen)["id"] if screen else None
        cap = LEVELS.get(level.upper(), 2)
        issues = [
            i
            for i in rep["issues"]
            if LEVELS.get(i["level"], 3) <= cap
            and (sid is None or i["screen"] == sid)
            and (include_triaged or i.get("triage", "open") in ("open", "confirmed"))
        ]
        titles = {s["id"]: s.get("title") for s in data["screens"]}
        by_screen: dict[str, dict] = {}
        for i in issues:
            row = by_screen.setdefault(
                i["screen"],
                {"screen": i["screen"], "title": titles.get(i["screen"]), "issues": 0, "criteria": set()},
            )
            row["issues"] += 1
            row["criteria"].add(i["sc"])
        screens = sorted(by_screen.values(), key=lambda r: -r["issues"])
        for r in screens:
            r["criteria"] = sorted(r["criteria"])
        return {
            "run": data["run"]["id"],
            "standard": rep.get("standard"),
            "level": level.upper(),
            "issues": len(issues),
            "screens": screens,
            "findings": [_issue(i) for i in issues[:100]],
            "truncated": len(issues) > 100,
            "report": str(d / "a11y-report.html") if (d / "a11y-report.html").is_file() else None,
        }

    def perf_summary(self, run: str | None = None) -> dict:
        """Navigation performance: load time per screen (slowest first), slow transitions, cold start."""
        rep = self._perf(self._run_dir(run))
        return {
            k: rep.get(k) for k in ("run", "budget_ms", "animations", "startup", "screens", "findings")
        } | {"transitions": (rep.get("transitions") or [])[:15]}

    # ── device ───────────────────────────────────────────────────────────────
    def _replayer(self, data: dict, serial: str | None):
        from .driver import AdbDriver
        from .replay import Replayer

        return Replayer(AdbDriver(serial or self.serial), data, log=lambda *a: None)

    def where_am_i(self, run: str | None = None, serial: str | None = None) -> dict:
        """Match the screen showing on the device right now to the map."""
        from .replay import identify

        _, data = self._data(run)
        rp = self._replayer(data, serial)
        obs = rp.observe()
        sid, sim, ranked = identify(obs, rp.app_screens)
        in_app = obs.package == rp.pkg
        return {
            "run": data["run"]["id"],
            "in_app": in_app,
            "package": obs.package,
            "activity": obs.activity,
            "screen": sid if in_app else None,
            "title": rp.screens[sid].get("title") if sid and in_app else None,
            "similarity": sim,
            "candidates": [{"id": s["id"], "title": s.get("title"), "similarity": v} for v, s in ranked[:3]],
            "visible": [e.label for e in obs.elements if e.action != "scroll"][:25],
        }

    def go_to_screen(
        self, screen: str, run: str | None = None, clear_data: bool = False, serial: str | None = None
    ) -> dict:
        """Drive the device to a screen: over recorded transitions from where it is now, else by
        relaunching the app and replaying the recorded path. The app is pinned while it moves."""
        from .replay import ReplayFailed

        _, data = self._data(run)
        target_screen = self._screen(data, screen)
        target = target_screen["id"]
        if not target_screen.get("reach_path") and target_screen.get("origin") != "launch":
            raise ValueError(f"{target} has no recorded path; it can only be reached by exploring")
        rp = self._replayer(data, serial)
        tried = []
        try:
            obs = rp.settled_observe()
            here, _ = rp.where(obs) if obs.package == rp.pkg else (None, 0.0)
            if here == target and not clear_data:
                return {"reached": True, "screen": target, "via": "already there", "steps": 0}
            path = shortest_path(data, here, target) if here and not clear_data else None
            if path:
                tried.append("graph")
                rp.d.pin(rp.pkg)
                try:
                    for i, st in enumerate(transition_steps(data, path)):
                        obs = rp.autofill(st["screen"], obs)
                        rp.step(st, obs)
                        obs = rp.settled_observe()
                        rp.check(obs, st["to"], i + 1)
                    return {
                        "reached": True,
                        "screen": target,
                        "via": "transitions",
                        "from": here,
                        "steps": len(path),
                    }
                except ReplayFailed:
                    pass
            tried.append("relaunch")
            try:
                arrivals = rp.replay(target, clear_data=clear_data)
            except ReplayFailed as e:
                return {
                    "reached": False,
                    "screen": target,
                    "tried": tried,
                    "reason": e.reason,
                    "detail": e.detail,
                }
            return {"reached": True, "screen": target, "via": "relaunch", "steps": len(arrivals) - 1}
        finally:
            rp.d.unpin()

    def crawl(
        self,
        package: str | None = None,
        apk: str | None = None,
        clear_data: bool = False,
        max_steps: int = 200,
        serial: str | None = None,
    ) -> dict:
        """Start mapping an app in the background (a crawl takes minutes). Poll crawl_status."""
        if not package and not apk:
            raise ValueError("pass package (installed app) or apk")
        logs = self.runs_root / ".mcp"
        logs.mkdir(parents=True, exist_ok=True)
        job = datetime.now().strftime("crawl-%Y%m%d-%H%M%S")
        cmd = [sys.executable, "-m", "appscreenmap.cli", "crawl", "--out", str(self.runs_root)]
        cmd += ["--apk", apk] if apk else ["--package", package]
        cmd += ["--max-steps", str(max_steps)] + (["--clear-data"] if clear_data else [])
        if serial or self.serial:
            cmd += ["--serial", serial or self.serial]
        log = logs / f"{job}.log"
        with log.open("w") as fh:
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        self._jobs[job] = {"proc": proc, "log": log, "started": time.time()}
        return {"job": job, "log": str(log), "status": "running"}

    def crawl_status(self, job: str | None = None) -> dict:
        """Progress of a crawl started with `crawl` (the latest one by default)."""
        if not self._jobs:
            raise ValueError("no crawl started from this server")
        job = job or max(self._jobs, key=lambda j: self._jobs[j]["started"])
        info = self._jobs.get(job)
        if info is None:
            raise ValueError(f"unknown job {job!r}")
        code = info["proc"].poll()
        text = info["log"].read_text(errors="replace") if info["log"].is_file() else ""
        out = {
            "job": job,
            "status": "running" if code is None else ("done" if code == 0 else "failed"),
            "exit_code": code,
            "log_tail": text.splitlines()[-12:],
        }
        if m := _RUN_DIR_RE.search(text):
            run_dir = Path(m.group(1))
            run_dir = run_dir if run_dir.is_absolute() else Path.cwd() / run_dir
            out["run"] = run_dir.name
            if (run_dir / "map.json").is_file():
                data = load_map(run_dir)
                out["steps"] = data["run"].get("steps")
                out["screens"] = data["stats"]["screens"]
                out["run_status"] = data["run"]["status"]
        return out


def _with_next(path: list[dict], target: str):
    for i, st in enumerate(path):
        yield st, (path[i + 1]["screen"] if i + 1 < len(path) else target)


def _issue(i: dict) -> dict:
    return {
        k: i.get(k)
        for k in ("screen", "rule", "sc", "level", "severity", "label", "detail", "bounds", "triage")
    }


def build_server(tools: MapTools):
    """Register MapTools with the MCP SDK."""
    from mcp.server.mcpserver import Image, MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp_types import ToolAnnotations

    from . import __version__
    from .config import MissingSecret
    from .driver import DriverError

    def expected(fn):
        """Pass anticipated failures to the agent as tool errors. The SDK hides the message of any
        other exception, and 'no screen X; see list_screens' is meant to be read."""

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (ValueError, DriverError, MissingSecret) as e:
                raise ToolError(str(e)) from e

        return wrapper

    server = MCPServer("appscreenmap", instructions=INSTRUCTIONS, version=__version__)

    def add(fn, annotations):
        server.add_tool(expected(fn), annotations=annotations)

    read = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    for fn in (
        tools.list_runs,
        tools.list_screens,
        tools.find_screens,
        tools.get_screen,
        tools.route,
        tools.a11y_findings,
        tools.perf_summary,
    ):
        add(fn, read)

    def screenshot(screen, run=None, full=False):
        """A screen's screenshot from the map (a thumbnail unless full=True)."""
        return Image(path=tools.screenshot_path(screen, run, full))

    # Real objects, not strings: the SDK evaluates annotations in this module, where Image isn't global.
    screenshot.__annotations__ = {"screen": str, "run": str | None, "full": bool, "return": Image}

    add(screenshot, read)
    add(tools.where_am_i, read)
    # Both drive the device and, with clear_data, wipe the app's data.
    acts = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)
    add(tools.go_to_screen, acts)
    add(tools.crawl, acts)
    add(tools.crawl_status, read)
    return server
