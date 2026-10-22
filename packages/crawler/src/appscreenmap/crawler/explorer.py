"""The crawl loop: greedy DFS over unexplored actions, backtracking via graph paths or restart + replay."""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from appscreenmap.core import accounts
from appscreenmap.core.analyzer import (
    PERMISSION_ALLOW_IDS,
    ElementInfo,
    Observation,
    analyze,
    is_crash_dialog,
    is_permission_dialog,
    jaccard,
)
from appscreenmap.core.config import CrawlConfig, placeholders, resolve
from appscreenmap.core.media import save_thumbnail
from appscreenmap.core.model import AppMap, Element, Screen, Step, Transition, selector_for
from appscreenmap.core.timeline import TIMELINE
from appscreenmap.drivers.android import AdbDriver
from appscreenmap.drivers.base import DriverError

from .timing import LoadMeter, Timing, has_loading_indicator

SCROLL_SAME_SCREEN = 0.4  # token similarity above which a scrolled view is still the same screen
MAX_GRAPH_PATH = 8
IN_PLACE_FIXED_SIMILARITY = 0.9  # fixed chrome nearly identical…
IN_PLACE_SIMILARITY = 0.5  # …and the screen as a whole still mostly the same
MAX_DATA_RESETS = 5  # per crawl
PIN_TOAST_SECONDS = 2.5


class CrawlAborted(RuntimeError):
    pass


class _TimedInputs:
    """The driver, noting the wall-clock time of the latest input: a screen starts when the tap that opens it lands,
    not when it has finished loading, and the requests it makes while loading are its own."""

    INPUTS = frozenset({"tap", "long_press", "back", "swipe", "launch"})

    def __init__(self, driver) -> None:
        object.__setattr__(self, "_d", driver)
        object.__setattr__(self, "input_at", 0.0)

    def __setattr__(self, name, value) -> None:
        # Tests and callers set attributes on `explorer.d`; they belong to the real driver.
        object.__setattr__(self, name, value) if name == "input_at" else setattr(self._d, name, value)

    def __getattr__(self, name):
        attr = getattr(self._d, name)
        if name not in self.INPUTS:
            return attr

        def timed(*a, **kw):
            self.input_at = time.time()
            return attr(*a, **kw)

        return timed


class Explorer:
    def __init__(
        self,
        driver: AdbDriver,
        package: str,
        launch_activity: str | None,
        cfg: CrawlConfig,
        run_dir: Path,
        appmap: AppMap,
        log=print,
    ):
        self.d = _TimedInputs(driver)
        self.pkg = package
        self.launch_activity = launch_activity
        self.cfg = cfg
        self.dir = run_dir
        self.map = appmap
        self.log = log
        self.width, self.height = driver.screen_size()
        self.step = 0
        self.t0 = time.monotonic()
        self.cur: Screen | None = None
        self.obs: Observation | None = None
        self.restarts = 0
        self.data_resets = 0
        self.meter = (
            LoadMeter(driver, package, cfg.load_quiet_ms, cfg.load_timeout_s) if cfg.measure_load else None
        )
        self.last_new_step = 0
        self._warned_literal_password = False
        self._in_playbook = False
        self.stop_reason: str | None = None
        (run_dir / "screens").mkdir(parents=True, exist_ok=True)
        self._trace = (run_dir / "trace.jsonl").open("a")
        self._arrived: tuple[str, int, float] | None = None

    # ── public ───────────────────────────────────────────────────────────────
    def run(self) -> None:
        try:
            self.restart("start")
            if self.cur is None or self.cur.kind != "app":
                raise CrawlAborted(f"{self.pkg} did not reach a screen of its own after launch")
            if self.cfg.playbook.get("before"):
                self.run_playbook("before")
            while self.budget_left():
                if self.cur.kind != "app":
                    self.recover()
                    continue
                el = self.next_action(self.cur)
                if el is not None:
                    self.act(el, explore=True)
                    continue
                target, path = self.pick_frontier()
                if target is None:
                    self.stop_reason = "complete: nothing left to explore"
                    self.log("nothing left to explore")
                    break
                self.navigate(target, path)
            else:
                self.log(f"end: {self.stop_reason}")
            if self.cfg.playbook.get("after") and self.cur is not None and self.cur.kind == "app":
                self.run_playbook("after")
        finally:
            self._trace.close()
            self.save()

    # ── playbook: scripted steps before and after the exploration ────────────
    def run_playbook(self, phase: str) -> bool:
        """Run the config's [[playbook.<phase>]] steps. A step that fails (and is not `optional`) ends the playbook."""
        steps = self.cfg.playbook.get(phase) or []
        results, ok = [], True
        self._in_playbook = True
        self.log(f"playbook {phase}: {len(steps)} step(s)")
        try:
            for n, step in enumerate(steps, 1):
                desc = _describe(step)
                try:
                    done = self._play(step)
                except DriverError as e:
                    done = False
                    self.log(f"  ! {e}")
                results.append({"n": n, "step": desc, "ok": done})
                self.trace(playbook=phase, n=n, step=desc, ok=done)
                if not done and not step.get("optional"):
                    ok = False
                    self.log(f"  ! playbook {phase} stopped at step {n}: {desc}")
                    break
        finally:
            self._in_playbook = False
        self.map.run.setdefault("playbook", {})[phase] = {"ok": ok, "steps": results}
        self.save()
        return ok

    def _play(self, step: dict) -> bool:
        timeout = float(step.get("timeout", 10))
        if "pause" in step:
            time.sleep(float(step["pause"]))
            return True
        if "account" in step:
            accounts.mark(self.pkg, "created")
            self.log("  test account marked as created")
            return True
        if (
            "entry" in step
        ):  # this screen is another way in: the app opens here (e.g. once a first-launch sheet is gone)
            cur = self.cur
            if cur is None or cur.kind != "app":
                return False
            cur.origin, cur.depth, cur.reach_path = "launch", 0, []
            self.log(f"  {cur.id} is an entry point")
            self.save()
            return True
        if "restart" in step:  # relaunch the app: a logged-in app lands on its main screen
            self.restart("playbook")
            return self.cur is not None and self.cur.kind == "app"
        if "tap_at" in step:  # a spot with no clickable node, e.g. a link inside a text (screen fractions)
            fx, fy = step["tap_at"]
            self.log(f"  playbook tap at {fx:.2f},{fy:.2f}")
            src = self.cur
            self.d.tap(round(fx * self.width), round(fy * self.height))
            self.step += 1
            time.sleep(self.cfg.settle_seconds)
            dst, is_new = self.arrive(self.observe(), hint=src)
            if src is not None and src.kind == "app":  # an arrow for it, from a stand-in element at that spot
                x, y = round(fx * self.width), round(fy * self.height)
                key, label = f"POS|{fx:.2f},{fy:.2f}", f"Tap at {fx:.2f},{fy:.2f}"
                self._link(src, dst, is_new, key, "click", "link", label, (x - 1, y - 1, x + 1, y + 1))
            return True
        if "back" in step:
            src = self.cur
            if src is not None and "SYS|back" in src.elements:  # goes through act(): the arrow is recorded
                return self.act(src.elements["SYS|back"], explore=False)
            self.d.back()
            self.step += 1
            self.arrive(self.observe())
            return True
        if "scroll" in step:
            return self._play_scroll(step["scroll"])
        rx = re.compile(step.get("wait") or step.get("tap") or step["type"], re.IGNORECASE)
        found = self._wait_for(rx, "input" if "type" in step else "tap" if "tap" in step else "any", timeout)
        if "wait" in step:
            return found is not None
        if found is None:
            return False
        if "tap" in step:
            el = next((e for e in self.cur.elements.values() if e.info.key == found.key), None)
            if el is None:
                return False
            self.log(f"  playbook tap {found.label!r}")
            return self.act(el, explore=False)
        self._type_into(found, step["value"])
        return True

    def _link(self, src, dst, is_new, key, action, kind, label, bounds) -> None:
        """Record an arrow for something the playbook did that has no element of its own."""
        info = ElementInfo(
            key=key,
            kind=kind,
            action=action,
            label=label,
            cls="",
            rid="",
            text="",
            desc="",
            hint="",
            bounds=bounds,
        )
        self.record(src, Element(id="synthetic", info=info), dst, is_new, explore=False)

    def _wait_for(self, rx: re.Pattern, want: str, timeout: float) -> ElementInfo | None:
        """The first element on screen matching `rx` (clickable for tap, an input for type), polling until `timeout`."""
        deadline = time.monotonic() + timeout
        while True:
            obs = self.observe()
            if self.cur is None or self.obs is None or _xml_hash(obs) != _xml_hash(self.obs):
                src = self.cur
                dst, is_new = self.arrive(obs, hint=src)
                if src is not None and dst is not src and src.kind == "app" and dst.kind == "app":
                    # The app moved on by itself (a carousel, a page that finished loading): still an arrow.
                    self._link(
                        src, dst, is_new, f"AUTO|{dst.id}", "wait", "auto", "Moved on by itself", (0, 0, 0, 0)
                    )
            hits = [
                i for i in self.obs.elements if _matches(i, rx) and i.kind not in ("up", "back", "scroll")
            ]
            if want == "tap":
                hits = [i for i in hits if i.action in ("click", "long_click") and i.kind != "input"]
            if (
                want == "input"
            ):  # a real text field first; Compose and custom views often report a plain clickable
                hits = sorted(hits, key=lambda i: i.kind != "input")
            if hits:
                return hits[0]
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.8)

    def _type_into(self, info: ElementInfo, value: str) -> None:
        secret = bool(placeholders(value))
        self.log(f"  playbook type into {info.label!r}{' (secret)' if secret else ''}")
        self.d.tap(*_center(info.bounds))
        time.sleep(0.4)
        self.d.input_text(resolve(value))
        self.cur.autofill.append(
            {
                "key": info.key,
                "label": info.label,
                "rid": info.rid,
                "value": value,  # the placeholder for secrets, never the resolved value
                "secret": secret,
                "selector": selector_for(info),
            }
        )
        self.d.hide_keyboard()
        time.sleep(self.cfg.settle_seconds)
        self.obs = self.observe()
        if self.obs.package == self.pkg and (self.obs.activity or "") == (self.cur.activity or ""):
            self.map.merge_elements(self.cur, self.obs, 0)

    def _play_scroll(self, how: str) -> bool:
        scroller = next((e for e in self.obs.elements if e.action == "scroll"), None)
        if scroller is None:
            return False
        forward = how in ("end", "down")
        last = _xml_hash(self.obs)
        for _ in range(1 if how in ("down", "up") else 25):
            self._swipe(scroller, forward=forward, fast=True)
            self.obs = self.observe()
            if _xml_hash(self.obs) == last:
                break
            last = _xml_hash(self.obs)
        if how == "end":
            self._capture_extra(self.cur, "bottom")
        self.arrive(self.obs)
        return True

    def _capture_extra(self, screen: Screen, name: str) -> None:
        """A second screenshot of a screen in another state (scrolled to the bottom), kept next to the first."""
        safe = f"{screen.id.replace(':', '_')}-{name}"
        png = self.dir / "screens" / f"{safe}.png"
        try:
            self.d.screenshot(png)
            screen.captures[name] = f"screens/{safe}.png"
        except (DriverError, OSError) as e:
            self.log(f"  ! screenshot failed for {safe}: {e}")

    # ── budget / persistence ─────────────────────────────────────────────────
    def budget_left(self) -> bool:
        if self.step >= self.cfg.max_steps:
            self.stop_reason = f"step budget reached ({self.cfg.max_steps})"
        elif (time.monotonic() - self.t0) / 60 >= self.cfg.max_minutes:
            self.stop_reason = f"time budget reached ({self.cfg.max_minutes:g} min)"
        elif self.cfg.stop_after_no_new and self.step - self.last_new_step >= self.cfg.stop_after_no_new:
            self.stop_reason = (
                f"saturated: no new screen in the last {self.cfg.stop_after_no_new} steps "
                "(only known screens and patterns repeating)"
            )
        else:
            return True
        return False

    def save(self) -> None:
        self.map.run["steps"] = self.step
        self.map.run["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        self.map.run["stop_reason"] = self.stop_reason
        self.map.run["elapsed_s"] = round(time.monotonic() - self.t0, 1)
        self.map.save(self.dir / "map.json")

    def trace(self, **row) -> None:
        row = {"step": self.step, "t": round(time.monotonic() - self.t0, 2), **row}
        self._trace.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._trace.flush()

    # ── observation ──────────────────────────────────────────────────────────
    def observe(self) -> Observation:
        snap = self.d.snapshot()
        obs = analyze(
            snap.xml,
            None,
            snap.activity,
            self.width,
            self.height,
            long_click=self.cfg.long_click,
            explore_toggles=self.cfg.explore_toggles,
            is_blocked=self.cfg.is_blocked,
            is_blocked_id=self.cfg.is_blocked_id,
        )
        if obs.package and snap.package and obs.package != snap.package:
            obs.activity = None  # the focused window belongs to another app (dialog, keyboard, …)
        return obs

    def arrive(self, obs: Observation | None = None, hint: Screen | None = None) -> tuple[Screen, bool]:
        """Observe the device, deal with system UI, and identify (or register) the current screen."""
        obs = obs or self.observe()
        for _ in range(3):
            if self.cfg.allow_permission_dialogs and is_permission_dialog(obs):
                if not self._allow_permission(obs):
                    break
                obs = self.observe()
            else:
                break

        if is_crash_dialog(obs) or (obs.package != self.pkg and self._app_crashed()):
            screen, is_new = self._register_crash(obs)
        else:
            screen, is_new = self.identify(obs, hint)
        self.cur, self.obs = screen, obs
        self._mark_arrival(screen)
        if screen.kind == "app":
            screen.visits += 1
            self.map.add_back(screen)
            self.map.infer_global_nav(screen)
            self.map.apply_list_cap(screen, self.cfg.max_list_items)
            if self.cfg.fill_forms:
                self.autofill(screen)
        return self.cur, is_new

    def _mark_arrival(self, screen: Screen) -> None:
        """One timeline entry per screen per step, timed at the input that led here (or now, if it changed by itself)."""
        if self._arrived and self._arrived[:2] == (screen.id, self.step):
            return
        last_t = self._arrived[2] if self._arrived else 0.0
        t = self.d.input_at if self.d.input_at > last_t else time.time()
        self._arrived = (screen.id, self.step, t)
        # Rounded down: rounding up could move the switch past a request made a moment after the tap.
        entry = {
            "t": math.floor(t * 1000) / 1000,
            "step": self.step,
            "screen": screen.id,
            "title": screen.title,
        }
        with (self.dir / TIMELINE).open("a") as f:  # wall clock, to tie network and log rows to screens
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _same_after_in_place_change(hint: Screen, obs: Observation) -> bool:
        fixed = obs.fixed_tokens
        has_text = any(t.startswith(("T:", "D:")) for t in fixed)
        return (
            hint.kind == "app"
            and (hint.activity or "") == (obs.activity or "")
            and len(fixed) >= 4
            and has_text
            and jaccard(hint.fixed_tokens, fixed) >= IN_PLACE_FIXED_SIMILARITY
            and jaccard(hint.tokens, obs.tokens) >= IN_PLACE_SIMILARITY
        )

    def identify(self, obs: Observation, hint: Screen | None = None) -> tuple[Screen, bool]:
        if obs.package != self.pkg:
            sid = f"x:{obs.package}"
            if sid in self.map.screens:
                return self.map.screens[sid], False
            screen = self.map.new_screen(obs, self.step, kind="external")
            if obs.package and "launcher" in obs.package:
                screen.title = "Home screen (app exited)"
            self._capture(screen, obs)
            return screen, True

        app_screens = [s for s in self.map.screens.values() if s.kind == "app"]
        for s in app_screens:
            if obs.signature in s.signatures:
                self.map.merge_elements(s, obs, 0)
                return s, False
        best, best_sim = None, 0.0
        for s in app_screens:
            if (s.activity or "") != (obs.activity or ""):
                continue
            sim = jaccard(obs.tokens, s.tokens)
            if sim > best_sim:
                best, best_sim = s, sim
        if best is not None and best_sim >= self.cfg.similarity:
            best.signatures.add(obs.signature)
            self.map.merge_elements(best, obs, 0)
            return best, False
        if hint is not None and self._same_after_in_place_change(hint, obs):
            # The action changed only scrolled content (scrolled into view, expanded a WebView…):
            # the fixed part (title, toolbar, nav) is unchanged, so it's still the same screen.
            hint.signatures.add(obs.signature)
            self.map.merge_elements(hint, obs, 0)
            return hint, False

        screen = self.map.new_screen(obs, self.step)
        self._capture(screen, obs)
        self.log(
            f"  new screen {screen.id}: {screen.title!r} [{obs.activity_short}] {','.join(screen.patterns)}"
        )
        return screen, True

    def _capture(self, screen: Screen, obs: Observation) -> None:
        safe = screen.id.replace(":", "_")
        png = self.dir / "screens" / f"{safe}.png"
        try:
            self.d.screenshot(png)
            screen.screenshot = f"screens/{safe}.png"
            jpg = png.with_suffix(".jpg")
            save_thumbnail(png, jpg)
            screen.thumb = f"screens/{safe}.jpg"
        except (DriverError, OSError) as e:
            self.log(f"  ! screenshot failed for {screen.id}: {e}")
        (self.dir / "screens" / f"{safe}.xml").write_text(obs.xml)
        screen.hierarchy = f"screens/{safe}.xml"

    def _app_crashed(self) -> bool:
        """The app left the foreground: did it crash? (Android 10+ often shows no dialog.)"""
        try:
            return f"Process: {self.pkg}," in self.d.crash_log()
        except DriverError:
            return False

    def _allow_permission(self, obs: Observation) -> bool:
        node = obs.find_rid(*PERMISSION_ALLOW_IDS)
        if node is None:
            return False
        self.d.tap(*node.center)
        self.map.events.append(
            {"step": self.step, "type": "permission", "detail": node.text or node.short_rid}
        )
        self.log(f"  allowed a permission dialog ({node.text or node.short_rid})")
        time.sleep(self.cfg.settle_seconds)
        return True

    def _register_crash(self, obs: Observation) -> tuple[Screen, bool]:
        n = len([e for e in self.map.events if e["type"] == "crash"]) + 1
        log_text = ""
        try:
            log_text = self.d.crash_log()
            (self.dir / "crashes").mkdir(exist_ok=True)
            (self.dir / "crashes" / f"crash-{n}.txt").write_text(log_text)
            self.d.clear_crash_log()
        except DriverError:
            pass
        self.map.events.append(
            {
                "step": self.step,
                "type": "crash",
                "screen": self.cur.id if self.cur else None,
                "detail": next(
                    (t for t in obs.texts() if "stop" in t.lower() or "respond" in t.lower()), "crash"
                ),
                "log": f"crashes/crash-{n}.txt" if log_text else None,
            }
        )
        self.log("  app crashed")
        is_new = "crash" not in self.map.screens
        screen = self.map.screens.get("crash") or self.map.new_screen(obs, self.step, kind="crash")
        if is_new:
            screen.title = "App crash"
            self._capture(screen, obs)
        close = obs.find_rid("aerr_close", "aerr_wait")
        if close is not None:
            self.d.tap(*close.center)
        elif is_crash_dialog(obs):
            self.d.back()
        # Recent Android shows no dialog for a first crash: the app is just gone (restart() relaunches it).
        return screen, is_new

    def autofill(self, screen: Screen) -> None:
        if self._in_playbook:
            return  # a playbook types its own values
        assert self.obs is not None
        empty = [
            e for e in self.obs.elements if e.kind == "input" and (not e.text.strip() or e.text == e.hint)
        ][:6]
        if not empty:
            return
        filled = []
        for info in empty:
            hints = (info.rid, info.hint, info.text, info.desc, info.label)
            value = self.cfg.input_for("password", *hints) if info.password else self.cfg.input_for(*hints)
            secret = bool(placeholders(value))
            if info.password and not secret and not self._warned_literal_password:
                self._warned_literal_password = True
                self.log("  ! typed a literal password; use ${ENV} in [inputs] to keep it out of the run")
            self.d.tap(*_center(info.bounds))
            time.sleep(0.3)
            self.d.input_text(resolve(value))
            filled.append(
                {
                    "key": info.key,
                    "label": info.label,
                    "rid": info.rid,
                    "value": value,  # the placeholder for secrets, never the resolved value
                    "secret": secret,
                    "selector": selector_for(info),
                }
            )
        self.d.hide_keyboard()
        time.sleep(self.cfg.settle_seconds)
        if not screen.autofill:
            screen.autofill = filled
            self.log(f"  filled {len(filled)} field(s): {', '.join(f['label'] for f in filled)}")
        obs = self.observe()
        self.obs = obs
        if obs.package == self.pkg and (obs.activity or "") == (screen.activity or ""):
            self.map.merge_elements(screen, obs, 0)
        else:
            self.log("  ! typing moved us to another screen; re-identifying")
            self.cur, _ = self.identify(obs)
            # Typing alone changed the context: a WCAG 3.2.2 (On Input) candidate.
            self.map.events.append(
                {
                    "step": self.step,
                    "type": "change_on_input",
                    "screen": screen.id,
                    "detail": f"typing into {', '.join(f['label'] for f in filled)} opened {self.cur.id}",
                }
            )

    # ── choosing what to do ──────────────────────────────────────────────────
    def next_action(self, screen: Screen) -> Element | None:
        self.map.infer_global_nav(screen)
        if screen.depth >= self.cfg.max_depth:
            for e in screen.pending():
                if e.info.kind != "back":
                    e.status, e.note = "skipped", f"max depth {self.cfg.max_depth}"
        if self.cfg.tab_tour:
            self._limit_tour(screen)
        pending = screen.pending()
        return pending[0] if pending else None

    def _limit_tour(self, screen: Screen) -> None:
        """Tab tour: once `tour_taps` content elements were tried on a screen, the rest are left alone. Navigation
        (tabs, bottom nav, up, back) and scrolling are never limited."""
        structural = {"nav", "tab", "up", "back", "scroll"}
        tried = sum(
            1 for e in screen.elements.values() if e.status != "pending" and e.info.kind not in structural
        )
        if tried < self.cfg.tour_taps:
            return
        for e in screen.pending():
            if e.info.kind not in structural:
                e.status, e.note = "skipped", f"tab tour: {self.cfg.tour_taps} tap(s) per screen"

    def routes(self, src: Screen) -> tuple[dict[str, float], dict[str, Transition]]:
        """Dijkstra over known edges. Back/up edges cost more: where they lead depends on history."""
        dist: dict[str, float] = {src.id: 0.0}
        prev: dict[str, Transition] = {}
        heap = [(0.0, src.id)]
        while heap:
            d, sid = heapq.heappop(heap)
            if d > dist.get(sid, float("inf")):
                continue
            for t in self.map.out_edges(sid):
                dst = self.map.screens[t.dst]
                if dst.kind != "app" or t.action == "scroll":
                    continue
                cost = d + (3.0 if t.kind in ("back", "up") else 1.0) + (0.5 if t.inferred else 0.0)
                if cost < dist.get(t.dst, float("inf")):
                    dist[t.dst], prev[t.dst] = cost, t
                    heapq.heappush(heap, (cost, t.dst))
        return dist, prev

    @staticmethod
    def _path(prev: dict[str, Transition], target: str) -> list[Transition]:
        path: list[Transition] = []
        while target in prev:
            path.append(prev[target])
            target = prev[target].src
        return path[::-1]

    def pick_frontier(self) -> tuple[Screen | None, list[Transition] | None]:
        candidates = [
            s
            for s in self.map.screens.values()
            if s.kind == "app" and s.nav_failures < 2 and s.pending() and s.depth < self.cfg.max_depth
        ]
        if not candidates:
            return None, None
        dist, prev = self.routes(self.cur)
        reachable = [s for s in candidates if s.id in dist]
        if reachable:
            target = min(reachable, key=lambda s: (dist[s.id], s.depth, s.first_step))
            path = self._path(prev, target.id)
            if len(path) <= MAX_GRAPH_PATH:
                return target, path
        return min(candidates, key=lambda s: (s.depth, s.first_step)), None

    def follow(self, path: list[Transition], target: Screen) -> bool:
        for t in path:
            if self.cur.id != t.src or not self.budget_left():
                return False
            self.act(self.map.screens[t.src].elements[t.key], explore=False)
        return self.cur is target

    # ── doing things ─────────────────────────────────────────────────────────
    def act(self, el: Element, explore: bool) -> bool:
        """Perform one element's action on the current screen and record what happened."""
        src = self.cur
        info = self.locate(el)
        if info is None and el.revealed_by and self._replay_reveal(el):
            src, info = self.cur, self.locate(el)
        if info is None:
            if explore:
                el.status, el.effect = "failed", "not_found"
                self.trace(screen=src.id, key=el.key, label=el.info.label, result="not_found")
                self.save()
            return False

        self.log(f"[{self.step + 1:>3}] {src.id} · {el.info.action} {el.info.label!r}")
        if el.info.action == "scroll":
            self.explore_scroll(el, info)
            return True

        if self.meter:
            self.meter.begin()
        if el.info.action == "click":
            self.d.tap(*_center(info.bounds))
        elif el.info.action == "long_click":
            self.d.long_press(*_center(info.bounds))
        elif el.info.action == "back":
            self.d.back()
        self.step += 1
        known_before = set(src.elements)
        timing, obs = self.wait_after_action()
        dst, is_new = self.arrive(obs, hint=src)
        if dst is src and el.info.action != "back":
            # Elements this action revealed on the same screen need it replayed before them.
            step = self._step(src, el)
            for key in set(src.elements) - known_before:
                src.elements[key].revealed_by = [*el.revealed_by, step]
        self.record(src, el, dst, is_new, explore, timing)
        return True

    @staticmethod
    def _step(src: Screen, el: Element) -> Step:
        return Step(src.id, el.key, el.info.action, el.info.label, selector_for(el.info), el.scroll_depth)

    def _replay_reveal(self, el: Element) -> bool:
        """Perform the same-screen steps that make `el` appear; True if we're still on that screen."""
        screen = self.cur
        for st in el.revealed_by:
            prior = screen.elements.get(st.key)
            if prior is None or self.cur is not screen or not self.act(prior, explore=False):
                return False
        return self.cur is screen

    def wait_after_action(self) -> tuple[Timing | None, Observation | None]:
        """Wait until the app has finished drawing (or a fixed sleep when not measuring)."""
        if not self.meter:
            time.sleep(self.cfg.settle_seconds)
            return None, None
        settled, secs = self.meter.wait_settled()
        obs = self.observe()
        waited = False
        if settled and obs.package == self.pkg and has_loading_indicator(obs.root):
            # Content is still on its way: wait for the frames that bring it, then settle again.
            settled, secs = self.meter.wait_settled(until_new_frames=True)
            obs, waited = self.observe(), True
        return self.meter.finish(settled, secs, waited), obs

    def record(
        self, src: Screen, el: Element, dst: Screen, is_new: bool, explore: bool, timing: Timing | None = None
    ) -> None:
        if dst is src:
            effect = "same_screen"
        else:
            t = self.map.add_transition(src, dst, el, self.step)
            if timing is not None and dst.kind == "app" and len(t.timings) < 20:
                t.timings.append(timing.to_dict())
            effect = {"external": "left_app", "crash": "crash"}.get(
                dst.kind, "new_screen" if is_new else "known_screen"
            )
            if dst.kind == "app" and (is_new or dst.origin == "unknown") and src.origin != "unknown":
                # First recorded way here (or a path for a screen first seen without one).
                # A bottom-bar tab is one tap from the tab root whichever screen the bar was tapped on, so the
                # tab's own screen hangs off the root (siblings), not off the previous tab.
                base = self._tab_root(src) if el.info.kind == "nav" and is_new else src
                revealed = el.revealed_by if base is src else []
                dst.reach_path = [*base.reach_path, *revealed, self._step(base, el)]
                # A tab tour counts a tab switch as the same level, so "one layer from each tab" means depth 1.
                same_level = self.cfg.tab_tour and el.info.kind in ("nav", "tab")
                dst.depth, dst.origin = base.depth + (0 if same_level else 1), "action"
                if el.info.kind == "nav" and is_new:
                    dst.title = (
                        el.info.label
                    )  # the tab's name beats whatever its header says (a date, a greeting)
            if is_new and dst.kind == "app":
                self.last_new_step = self.step
                self.map.mark_variant(dst, src, el)
                if dst.title == (dst.activity or "").rsplit(".", 1)[-1] and el.info.kind != "back":
                    # No title on the screen itself (menus, sheets): name it after what opened it.
                    menu = "dialog" in dst.patterns or "list" in dst.patterns
                    dst.title = f"{el.info.label} menu" if menu else el.info.label
        if dst.kind == "external" and self.cfg.stay_in_app:
            note = f"leaves the app (opened {dst.package})"
            el.note = note
            self.map.block_everywhere(el.key, note)
        if explore:
            el.status, el.effect = "done", effect
            el.target = dst.id if dst is not src else None
        self.trace(
            screen=src.id,
            key=el.key,
            action=el.info.action,
            label=el.info.label,
            to=dst.id,
            effect=effect,
            explore=explore,
            **({"load_ms": timing.load_ms, "settled": timing.settled} if timing else {}),
        )
        self.save()

    def locate(self, el: Element) -> ElementInfo | None:
        """Find the element on screen now, scrolling down to look for it if needed."""
        if el.info.action == "back":
            return el.info
        info = self.obs.element(el.key)
        if info is not None:
            return info
        scroller = next((e for e in self.obs.elements if e.action == "scroll" and e.direction == "up"), None)
        if scroller is None:
            return None
        last = _xml_hash(self.obs)
        for _ in range(max(1, el.scroll_depth) + 1):
            self._swipe(scroller, forward=True)
            self.obs = self.observe()
            if (info := self.obs.element(el.key)) is not None:
                return info
            if _xml_hash(self.obs) == last:
                break
            last = _xml_hash(self.obs)
        return None

    def explore_scroll(self, el: Element, info: ElementInfo) -> None:
        """Scroll a container to its end (bounded), adding newly revealed elements to the screen."""
        src = self.cur
        last, swipes, revealed = _xml_hash(self.obs), 0, 0
        for i in range(1, self.cfg.max_scrolls + 1):
            self._swipe(info, forward=True)
            swipes += 1
            self.step += 1
            obs = self.observe()
            if _xml_hash(obs) == last:
                break
            last = _xml_hash(obs)
            same = obs.package == self.pkg and (
                obs.signature in src.signatures
                or (
                    (obs.activity or "") == (src.activity or "")
                    and jaccard(obs.tokens, src.tokens) >= SCROLL_SAME_SCREEN
                )
            )
            if not same:
                # Swiping changed the screen (pager, pull-to-refresh into a new view, …): a real transition.
                dst, is_new = self.arrive()
                self.record(src, el, dst, is_new, explore=True)
                return
            revealed += self.map.merge_elements(src, obs, i)
            self.obs = obs
        for _ in range(swipes):
            self._swipe(info, forward=False, fast=True)
        time.sleep(0.4)
        self.obs = self.observe()
        self.map.apply_list_cap(src, self.cfg.max_list_items)
        el.status, el.effect, el.note = "done", "same_screen", f"{swipes} swipe(s), {revealed} new element(s)"
        self.trace(
            screen=src.id,
            key=el.key,
            action="scroll",
            label=el.info.label,
            to=src.id,
            effect="same_screen",
            revealed=revealed,
        )
        self.save()

    def _swipe(self, info: ElementInfo, forward: bool, fast: bool = False) -> None:
        x1, y1, x2, y2 = info.bounds
        w, h = x2 - x1, y2 - y1
        ms = 250 if fast else 600
        if info.direction == "left":
            y = (y1 + y2) // 2
            a, b = int(x2 - w * 0.15), int(x1 + w * 0.15)
            self.d.swipe(a, y, b, y, ms) if forward else self.d.swipe(b, y, a, y, ms)
        else:
            x = (x1 + x2) // 2
            top = int(max(y1 + h * 0.2, self.height * 0.2))
            bottom = int(min(y2 - h * 0.2, self.height * 0.8))
            if bottom - top < 80:
                top, bottom = y1 + 10, y2 - 10
            self.d.swipe(x, bottom, x, top, ms) if forward else self.d.swipe(x, top, x, bottom, ms)
        time.sleep(0.5)

    # ── getting around ───────────────────────────────────────────────────────
    def restart(self, reason: str) -> None:
        self.restarts += 1
        if self.restarts > max(20, self.cfg.max_steps // 3):
            raise CrawlAborted("too many restarts; the app keeps leaving or crashing")
        self.log(f"  restart app ({reason})")
        self.d.force_stop(self.pkg)
        launch = self.d.launch(self.pkg, self.launch_activity)
        if launch:
            self.map.perf["startup"].append({"step": self.step, "reason": reason, **launch})
        if self.meter:
            # am start -W returns at the first frame; wait for the content to finish drawing too.
            self.meter.begin()
            self.meter.wait_settled()
        else:
            time.sleep(self.cfg.launch_wait_seconds)
        if self.cfg.stay_in_app:
            if self.d.pin(self.pkg):
                time.sleep(PIN_TOAST_SECONDS)  # let the "App pinned" toast fade before screenshots
            else:
                self.log("  ! could not pin the app; it may still leave via BACK or links")
        self.step += 1
        self.map.events.append({"step": self.step, "type": "restart", "detail": reason})
        screen, _ = self.arrive()
        if screen.kind == "app" and screen.origin == "unknown":
            # Launch lands here (the first screen, or a different start screen after login / restored state).
            screen.reach_path, screen.depth, screen.origin = [], 0, "launch"
            if "bottom_nav" in screen.patterns and (tab := self._selected_tab()):
                screen.title = tab
        self.save()

    def _selected_tab(self) -> str | None:
        """The label of the highlighted bottom-bar tab on screen now."""
        tab = (
            next((e for e in self.obs.elements if e.kind == "nav" and e.selected), None) if self.obs else None
        )
        return tab.label if tab else None

    def _tab_root(self, src: Screen) -> Screen:
        """The screen the bottom bar hangs off: the launch screen that shows it, else the screen it was tapped on."""
        root = next(
            (s for s in self.map.screens.values() if s.origin == "launch" and "bottom_nav" in s.patterns),
            None,
        )
        return root or src

    def recover(self) -> None:
        """We are outside the app (external app, launcher, crash dialog): get back in."""
        if (
            not self.cfg.stay_in_app
            and self.cur.kind == "external"
            and "launcher" not in (self.cur.package or "")
        ):
            self.d.back()
            self.step += 1
            time.sleep(self.cfg.settle_seconds)
            screen, _ = self.arrive()
            if screen.kind == "app":
                return
        self.restart(f"recover from {self.cur.id}")

    def _first_run_only(self, target: Screen) -> bool:
        """The target is the first screen of the crawl, or only reachable through it."""
        first = _first_run_screen_ids(self.map.screens.values())
        if target.id in first:
            return True
        return bool(target.reach_path) and target.reach_path[0].screen in first

    def navigate(self, target: Screen, path: list[Transition] | None) -> bool:
        self.log(f"  navigate to {target.id} ({target.title!r})")
        if path and self.follow(path, target):
            return True
        self.restart(f"route to {target.id}")
        if self.cur is target:
            return True
        # Route from wherever launch put us (apps often reopen on the last-used tab).
        if self.cur.kind == "app":
            dist, prev = self.routes(self.cur)
            if target.id in dist and self.follow(self._path(prev, target.id), target):
                return True
        # Last resort: replay the exact steps that first reached the target.
        if target.reach_path and self.cur.id == target.reach_path[0].screen:
            for st in target.reach_path:
                if self.cur.id != st.screen or not self.budget_left():
                    break
                el = self.map.screens[st.screen].elements.get(st.key)
                if el is None or not self.act(el, explore=False):
                    break
            if self.cur is target:
                return True
        # First-run screens (onboarding, sign-in) vanish once the app saves state. With --clear-data the
        # user allowed wiping app data, so reset it once to get back to them.
        if self.cfg.clear_data and self._first_run_only(target) and self.data_resets < MAX_DATA_RESETS:
            self.data_resets += 1
            self.log(f"  ⟲ reset app data to reach first-run screen {target.id}")
            self.map.events.append({"step": self.step, "type": "data_reset", "detail": target.id})
            self.d.clear_data(self.pkg)
            if self.cfg.grant_permissions:
                self.d.grant_all(self.pkg)
            self.restart(f"route to {target.id} after data reset")
            if self.cur is target:
                return True
            if self.cur.kind == "app":
                dist, prev = self.routes(self.cur)
                if target.id in dist and self.follow(self._path(prev, target.id), target):
                    return True
        target.nav_failures += 1
        self.map.events.append({"step": self.step, "type": "nav_failed", "detail": target.id})
        self.log(f"  could not reach {target.id} (attempt {target.nav_failures})")
        if target.nav_failures >= 2:
            for e in target.pending():
                e.status, e.note = "unreachable", "could not navigate back to this screen"
        return False


def _first_run_screen_ids(screens) -> set[str]:
    return {s.id for s in screens if s.kind == "app" and s.origin == "launch" and s.first_step <= 2}


def _describe(step: dict) -> str:
    action = next(
        a
        for a in ("tap", "tap_at", "type", "wait", "scroll", "back", "restart", "pause", "account", "entry")
        if a in step
    )
    return f"{action} {step[action]!r}" if action not in ("back", "restart") else action


def _matches(info: ElementInfo, rx: re.Pattern) -> bool:
    rid = info.rid.rsplit("/", 1)[-1] if info.rid else ""
    return any(rx.search(v) for v in (info.label, rid, info.text, info.desc, info.hint) if v)


def _center(bounds) -> tuple[int, int]:
    x1, y1, x2, y2 = bounds
    return (x1 + x2) // 2, (y1 + y2) // 2


def _xml_hash(obs: Observation) -> str:
    return hashlib.sha1(obs.xml.encode()).hexdigest()
