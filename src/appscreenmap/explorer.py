"""The crawl loop: greedy DFS over unexplored actions, backtracking via graph paths or restart + replay."""

from __future__ import annotations

import hashlib
import heapq
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from .analyzer import (
    PERMISSION_ALLOW_IDS,
    ElementInfo,
    Observation,
    analyze,
    is_crash_dialog,
    is_permission_dialog,
    jaccard,
)
from .config import CrawlConfig, placeholders, resolve
from .driver import AdbDriver, DriverError
from .media import save_thumbnail
from .model import AppMap, Element, Screen, Step, Transition, selector_for
from .perf import LoadMeter, Timing, has_loading_indicator

SCROLL_SAME_SCREEN = 0.4  # token similarity above which a scrolled view is still the same screen
MAX_GRAPH_PATH = 8
MAX_DATA_RESETS = 5  # per crawl
PIN_TOAST_SECONDS = 2.5


class CrawlAborted(RuntimeError):
    pass


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
        self.d = driver
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
        self.stop_reason: str | None = None
        (run_dir / "screens").mkdir(parents=True, exist_ok=True)
        self._trace = (run_dir / "trace.jsonl").open("a")

    # ── public ───────────────────────────────────────────────────────────────
    def run(self) -> None:
        try:
            self.restart("start")
            if self.cur is None or self.cur.kind != "app":
                raise CrawlAborted(f"{self.pkg} did not reach a screen of its own after launch")
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
                    self.log("✔ nothing left to explore")
                    break
                self.navigate(target, path)
            else:
                self.log(f"⏹ {self.stop_reason}")
        finally:
            self._trace.close()
            self.save()

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
        )
        if obs.package and snap.package and obs.package != snap.package:
            obs.activity = None  # the focused window belongs to another app (dialog, keyboard, …)
        return obs

    def arrive(self, obs: Observation | None = None) -> tuple[Screen, bool]:
        """Observe the device, deal with system UI, and identify (or register) the current screen."""
        obs = obs or self.observe()
        for _ in range(3):
            if self.cfg.allow_permission_dialogs and is_permission_dialog(obs):
                if not self._allow_permission(obs):
                    break
                obs = self.observe()
            else:
                break

        if is_crash_dialog(obs):
            screen, is_new = self._register_crash(obs)
        else:
            screen, is_new = self.identify(obs)
        self.cur, self.obs = screen, obs
        if screen.kind == "app":
            screen.visits += 1
            self.map.add_back(screen)
            self.map.infer_global_nav(screen)
            self.map.apply_list_cap(screen, self.cfg.max_list_items)
            if self.cfg.fill_forms:
                self.autofill(screen)
        return self.cur, is_new

    def identify(self, obs: Observation) -> tuple[Screen, bool]:
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

        screen = self.map.new_screen(obs, self.step)
        self._capture(screen, obs)
        self.log(
            f"  ★ new screen {screen.id}: {screen.title!r} [{obs.activity_short}] {','.join(screen.patterns)}"
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

    def _allow_permission(self, obs: Observation) -> bool:
        node = obs.find_rid(*PERMISSION_ALLOW_IDS)
        if node is None:
            return False
        self.d.tap(*node.center)
        self.map.events.append(
            {"step": self.step, "type": "permission", "detail": node.text or node.short_rid}
        )
        self.log(f"  🔓 allowed permission dialog ({node.text or node.short_rid})")
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
        self.log("  💥 app crashed")
        is_new = "crash" not in self.map.screens
        screen = self.map.screens.get("crash") or self.map.new_screen(obs, self.step, kind="crash")
        if is_new:
            screen.title = "App crash"
            self._capture(screen, obs)
        close = obs.find_rid("aerr_close", "aerr_wait")
        if close is not None:
            self.d.tap(*close.center)
        else:
            self.d.back()
        return screen, is_new

    def autofill(self, screen: Screen) -> None:
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
            self.log(f"  ⌨ filled {len(filled)} field(s): {', '.join(f['label'] for f in filled)}")
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
        pending = screen.pending()
        return pending[0] if pending else None

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
        timing, obs = self.wait_after_action()
        dst, is_new = self.arrive(obs)
        self.record(src, el, dst, is_new, explore, timing)
        return True

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
                dst.reach_path = [
                    *src.reach_path,
                    Step(
                        src.id, el.key, el.info.action, el.info.label, selector_for(el.info), el.scroll_depth
                    ),
                ]
                dst.depth, dst.origin = src.depth + 1, "action"
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
        self.log(f"  ↻ restart app ({reason})")
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
        self.save()

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
        self.log(f"  → navigate to {target.id} ({target.title!r})")
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
        self.log(f"  ✗ could not reach {target.id} (attempt {target.nav_failures})")
        if target.nav_failures >= 2:
            for e in target.pending():
                e.status, e.note = "unreachable", "could not navigate back to this screen"
        return False


def _first_run_screen_ids(screens) -> set[str]:
    return {s.id for s in screens if s.kind == "app" and s.origin == "launch" and s.first_step <= 2}


def _center(bounds) -> tuple[int, int]:
    x1, y1, x2, y2 = bounds
    return (x1 + x2) // 2, (y1 + y2) // 2


def _xml_hash(obs: Observation) -> str:
    return hashlib.sha1(obs.xml.encode()).hexdigest()
