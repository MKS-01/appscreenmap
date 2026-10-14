"""Replay a map on a device: recognise the live screen, and walk a screen's recorded path to it.

Shared by `appscreenmap verify` (replay every path on a new build) and the MCP server
(`where_am_i`, `go_to_screen`). Works from `map.json` dicts, so it needs no crawl state.

A path is a screen's `reach_path`: steps from a fresh launch, each one an action on a known screen.
Before each step, fields the crawl typed on that screen (`autofill`) are typed again, with `${ENV}`
placeholders filled from the environment. Elements are found by key, then resource id, then text or
description, then label. A recorded point is only tapped when the element never had any of those
(as in the Maestro flows).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from appscreenmap.core.analyzer import (
    PERMISSION_ALLOW_IDS,
    ElementInfo,
    Observation,
    analyze,
    is_crash_dialog,
    is_permission_dialog,
    jaccard,
)
from appscreenmap.core.config import resolve

from .timing import LoadMeter, has_loading_indicator

MATCH_THRESHOLD = 0.6  # token similarity at which a live screen is a map screen (as in `diff`)
BEST_MARGIN = 0.02  # the expected screen wins if it is this close to the best match
PIN_TOAST_SECONDS = 2.5


def rank_screens(obs: Observation, screens: list[dict]) -> list[tuple[float, dict]]:
    """Map screens by similarity to an observation, best first."""
    ranked = []
    for s in screens:
        if s.get("kind") != "app":
            continue
        if obs.signature == s.get("signature"):
            sim = 1.0
        else:
            sim = jaccard(obs.tokens, frozenset(s.get("tokens", [])))
            if (s.get("activity") or "").rsplit(".", 1)[-1] == (obs.activity or "").rsplit(".", 1)[-1]:
                sim = min(1.0, sim + 0.05)
        ranked.append((round(sim, 3), s))
    ranked.sort(key=lambda r: -r[0])
    return ranked


def identify(
    obs: Observation, screens: list[dict], expected: str | None = None, threshold: float = MATCH_THRESHOLD
) -> tuple[str | None, float, list[tuple[float, dict]]]:
    """(screen id or None, similarity, ranking). The expected screen wins when it is (nearly) the best
    match, so look-alike screens (two states of one list) don't fail a path."""
    ranked = rank_screens(obs, screens)
    if not ranked:
        return None, 0.0, ranked
    best_sim, best = ranked[0]
    if expected:
        exp = next(((sim, s) for sim, s in ranked if s["id"] == expected), None)
        if exp and exp[0] >= threshold and exp[0] >= best_sim - BEST_MARGIN:
            return expected, exp[0], ranked
    if best_sim >= threshold:
        return best["id"], best_sim, ranked
    return None, best_sim, ranked


def find_element(
    obs: Observation, key: str, selector: dict, label: str = ""
) -> tuple[ElementInfo | None, str]:
    """The element a recorded step or autofill acts on, and how it was found."""
    if (el := obs.element(key)) is not None:
        return el, "key"
    els = obs.elements
    if rid := selector.get("id"):
        hits = [e for e in els if e.rid == rid]
        if len(hits) > 1 and selector.get("text"):
            hits = [e for e in hits if e.text.strip() == selector["text"]] or hits
        if hits:
            return hits[0], "id"
    for attr, how in (("text", "text"), ("desc", "desc")):
        want = selector.get(attr)
        if want and (hit := next((e for e in els if getattr(e, attr).strip() == want), None)):
            return hit, how
    if label and (hit := next((e for e in els if e.label == label and e.action != "scroll"), None)):
        return hit, "label"
    return None, ""


class ReplayFailed(Exception):
    """A step could not be performed, or it led somewhere other than the recorded path says."""

    def __init__(self, reason: str, index: int, detail: str, obs: Observation | None, got: str | None = None):
        super().__init__(detail)
        self.reason = reason  # not_found | wrong_screen | left_app | crash | not_launched | missing_secret
        # Arrival index on the path: 0 = right after launch, i = after step i-1. For not_found it is
        # the index of the step whose element is missing (taken on the i-th screen).
        self.index = index
        self.detail = detail
        self.obs = obs
        self.got = got


@dataclass
class Arrival:
    """One screen reached while replaying a path."""

    screen: str
    index: int  # 0 = after launch, i = after step i-1
    similarity: float
    obs: Observation
    load_ms: int | None = None
    via: str = ""  # how the step's element was found (key | id | text | desc | label | point)
    extra: dict = field(default_factory=dict)


class Replayer:
    def __init__(
        self, driver, data: dict, threshold: float = MATCH_THRESHOLD, measure: bool = True, log=print
    ):
        self.d = driver
        self.data = data
        self.log = log
        self.threshold = threshold
        app = data["run"]["app"]
        self.pkg: str = app["package"]
        self.launch_activity: str | None = app.get("launch_activity")
        self.cfg: dict = data["run"].get("config", {})
        self.screens = {s["id"]: s for s in data["screens"]}
        self.app_screens = [s for s in data["screens"] if s["kind"] == "app"]
        self.width, self.height = driver.screen_size()
        self.meter = (
            LoadMeter(
                driver, self.pkg, self.cfg.get("load_quiet_ms", 400), self.cfg.get("load_timeout_s", 10.0)
            )
            if measure
            else None
        )
        self.settle = self.cfg.get("settle_seconds", 0.8)

    # ── observing ────────────────────────────────────────────────────────────
    def observe(self) -> Observation:
        snap = self.d.snapshot()
        obs = analyze(
            snap.xml,
            None,
            snap.activity,
            self.width,
            self.height,
            long_click=self.cfg.get("long_click", False),
            explore_toggles=self.cfg.get("explore_toggles", True),
        )
        if obs.package and snap.package and obs.package != snap.package:
            obs.activity = None
        return obs

    def settled_observe(self) -> Observation:
        """Observe, allowing runtime permission dialogs on the way (like the crawl does)."""
        obs = self.observe()
        for _ in range(3):
            if not (self.cfg.get("allow_permission_dialogs", True) and is_permission_dialog(obs)):
                break
            node = obs.find_rid(*PERMISSION_ALLOW_IDS)
            if node is None:
                break
            self.d.tap(*node.center)
            time.sleep(self.settle)
            obs = self.observe()
        return obs

    def where(self, obs: Observation, expected: str | None = None) -> tuple[str | None, float]:
        sid, sim, _ = identify(obs, self.app_screens, expected, self.threshold)
        return sid, sim

    # ── acting ───────────────────────────────────────────────────────────────
    def _wait(self) -> int | None:
        if not self.meter:
            time.sleep(self.settle)
            return None
        settled, secs = self.meter.wait_settled()
        if settled and has_loading_indicator(self.observe().root):
            settled, secs = self.meter.wait_settled(until_new_frames=True)
        return round(secs * 1000)

    def launch(self, clear_data: bool = False, pin: bool = True) -> Observation:
        self.d.force_stop(self.pkg)
        if clear_data:
            self.d.clear_data(self.pkg)
            if self.cfg.get("grant_permissions", True):
                self.d.grant_all(self.pkg)
        if self.meter:
            self.meter.begin()
        self.d.launch(self.pkg, self.launch_activity)
        if self.meter:
            self.meter.wait_settled()
        else:
            time.sleep(self.cfg.get("launch_wait_seconds", 2.5))
        if pin and self.d.pin(self.pkg):
            time.sleep(PIN_TOAST_SECONDS)
        return self.settled_observe()

    def autofill(self, sid: str, obs: Observation) -> Observation:
        """Type what the crawl typed on this screen. Secrets are read from the environment here."""
        fields = self.screens.get(sid, {}).get("autofill") or []
        if not fields:
            return obs
        for f in fields:
            el, _ = find_element(obs, f["key"], f.get("selector", {}), f.get("label", ""))
            if el is not None:
                point = _center(el.bounds)
            elif f.get("selector", {}).get("point"):
                point = tuple(f["selector"]["point"])
            else:
                continue
            self.d.tap(*point)
            time.sleep(0.3)
            self.d.input_text(resolve(f["value"]))
        self.d.hide_keyboard()
        time.sleep(self.settle)
        return self.observe()

    def _scroll_find(self, obs: Observation, step: dict) -> tuple[ElementInfo | None, str, Observation]:
        scroller = next((e for e in obs.elements if e.action == "scroll" and e.direction == "up"), None)
        if scroller is None:
            return None, "", obs
        x1, y1, x2, y2 = scroller.bounds
        x = (x1 + x2) // 2
        top, bottom = (
            int(max(y1 + (y2 - y1) * 0.2, self.height * 0.2)),
            int(min(y2 - (y2 - y1) * 0.2, self.height * 0.8)),
        )
        for _ in range(max(1, step.get("scroll_depth", 0)) + 1):
            self.d.swipe(x, bottom, x, top, 600)
            time.sleep(0.5)
            obs = self.observe()
            el, via = find_element(obs, step["key"], step["selector"], step.get("label", ""))
            if el is not None:
                return el, via, obs
        return None, "", obs

    def step(self, step: dict, obs: Observation) -> tuple[str, int | None]:
        """Perform one recorded step. Returns (how the element was found, load ms)."""
        if step["action"] == "back":
            if self.meter:
                self.meter.begin()
            self.d.back()
            return "back", self._wait()
        el, via = find_element(obs, step["key"], step["selector"], step.get("label", ""))
        if el is None:
            el, via, obs = self._scroll_find(obs, step)
        sel = step["selector"]
        if el is not None:
            point = _center(el.bounds)
        elif not (sel.get("id") or sel.get("text") or sel.get("desc")) and sel.get("point"):
            point, via = tuple(sel["point"]), "point"
        else:
            raise ReplayFailed("not_found", -1, f"{step['label']!r} is not on {step['screen']}", obs)
        if self.meter:
            self.meter.begin()
        if step["action"] == "long_click":
            self.d.long_press(*point)
        else:
            self.d.tap(*point)
        return via, self._wait()

    def check(self, obs: Observation, expected: str, index: int) -> float:
        """Raise unless the observation is the expected screen. Returns the similarity."""
        if is_crash_dialog(obs):
            raise ReplayFailed("crash", index, "the app crashed", obs)
        if obs.package != self.pkg:
            raise ReplayFailed("left_app", index, f"left the app (now in {obs.package})", obs)
        sid, sim = self.where(obs, expected)
        if sid != expected:
            got = f"{sid} {self.screens[sid].get('title')!r}" if sid else "an unknown screen"
            raise ReplayFailed(
                "wrong_screen",
                index,
                f"expected {expected} {self.screens[expected].get('title')!r}, got {got}",
                obs,
                sid,
            )
        return sim

    def replay(self, target: str, clear_data: bool = False, on_arrival=None) -> list[Arrival]:
        """Launch fresh and walk `target`'s reach path, checking every screen on the way.

        `on_arrival(arrival)` is called for each screen reached (for screenshots). Raises ReplayFailed
        with `index` = the step that failed (len(path) for the final screen)."""
        screen = self.screens[target]
        path = screen.get("reach_path") or []
        expected = [st["screen"] for st in path] + [target]
        obs = self.launch(clear_data=clear_data)
        arrivals: list[Arrival] = []
        via, load_ms = "", None
        for i, sid in enumerate(expected):
            try:
                sim = self.check(obs, sid, i)
            except ReplayFailed as e:
                if i == 0 and e.reason == "wrong_screen":
                    e.reason = "not_launched"  # launch opened somewhere else (state, onboarding done)
                raise
            arrival = Arrival(sid, i, sim, obs, load_ms, via)
            arrivals.append(arrival)
            if on_arrival:
                on_arrival(arrival)
            if i == len(path):
                break
            if i == 0 or expected[i - 1] != sid:
                # Once per arrival: a path can take several steps on one screen (`revealed_by` steps
                # that make an element appear), and the fields are filled by then.
                obs = self.autofill(sid, obs)
            try:
                via, load_ms = self.step(path[i], obs)
            except ReplayFailed as e:
                e.index = i
                raise
            obs = self.settled_observe()
        return arrivals


def _center(bounds) -> tuple[int, int]:
    x1, y1, x2, y2 = bounds
    return (x1 + x2) // 2, (y1 + y2) // 2
