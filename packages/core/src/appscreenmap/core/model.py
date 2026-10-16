"""The app map: screens, their elements, transitions between them, and run metadata.

Serialized as `map.json` (schema 1), the single source of truth read by exports and the web viewer.
"""

from __future__ import annotations

import json
import os
import statistics
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .analyzer import KIND_PRIORITY, ElementInfo, Observation, weighted_jaccard

SCHEMA_VERSION = 1
LAYOUT_VARIANT = 0.85  # layout similarity at which two screens count as one template


@dataclass
class Element:
    id: str
    info: ElementInfo
    status: str = "pending"  # pending | done | blocked | skipped | failed | unreachable
    effect: str | None = None  # new_screen | known_screen | same_screen | left_app | crash | not_found
    target: str | None = None
    scroll_depth: int = 0
    note: str | None = None
    # Same-screen steps that made this element appear (e.g. "15 MIN" starts a timer that shows "OPEN").
    # Paths through this element replay them first.
    revealed_by: list[Step] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.info.key

    @property
    def priority(self) -> tuple:
        return (
            KIND_PRIORITY.get(self.info.kind, 5),
            self.scroll_depth,
            self.info.bounds[1],
            self.info.bounds[0],
        )

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            **self.info.to_dict(),
            "status": self.status,
            "effect": self.effect,
            "target": self.target,
            "scroll_depth": self.scroll_depth,
        }
        if self.note:
            d["note"] = self.note
        if self.revealed_by:
            d["revealed_by"] = [s.to_dict() for s in self.revealed_by]
        return d


@dataclass
class Step:
    """One action on a known screen; a list of steps from launch is a replayable path."""

    screen: str
    key: str
    action: str
    label: str
    selector: dict
    scroll_depth: int = 0

    def to_dict(self) -> dict:
        return {
            "screen": self.screen,
            "key": self.key,
            "action": self.action,
            "label": self.label,
            "selector": self.selector,
            "scroll_depth": self.scroll_depth,
        }


@dataclass
class Screen:
    id: str
    kind: str  # app | external | crash
    signature: str
    tokens: frozenset[str]
    package: str | None
    activity: str | None
    title: str
    patterns: list[str]
    width: int = 0
    height: int = 0
    elements: dict[str, Element] = field(default_factory=dict)
    reach_path: list[Step] = field(default_factory=list)
    autofill: list[dict] = field(default_factory=list)
    depth: int = 0
    visits: int = 0
    first_step: int = 0
    signatures: set[str] = field(default_factory=set)
    nav_failures: int = 0
    screenshot: str | None = None
    thumb: str | None = None
    hierarchy: str | None = None
    captures: dict[str, str] = field(
        default_factory=dict
    )  # extra shots, e.g. {"bottom": "screens/s012-bottom.png"}
    # How the screen is reached: "launch" (app start lands here; reach_path is []), "action" (reach_path
    # replays from launch), or "unknown" (first seen outside a recorded action, e.g. after returning from
    # another app or when typing changed screens; healed as soon as a known screen leads here).
    origin: str = "unknown"
    variant_of: str | None = (
        None  # same layout as another screen, different data (e.g. 2nd list item's detail)
    )

    layout: Counter = field(default_factory=Counter)
    fixed_tokens: frozenset[str] = frozenset()

    def pending(self) -> list[Element]:
        return sorted((e for e in self.elements.values() if e.status == "pending"), key=lambda e: e.priority)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "activity": self.activity,
            "package": self.package,
            "signature": self.signature,
            "patterns": self.patterns,
            "depth": self.depth,
            "visits": self.visits,
            "first_step": self.first_step,
            "width": self.width,
            "height": self.height,
            "screenshot": self.screenshot,
            "thumb": self.thumb,
            "hierarchy": self.hierarchy,
            "captures": self.captures,
            "variant_of": self.variant_of,
            "origin": self.origin,
            "reach_path": [s.to_dict() for s in self.reach_path],
            "autofill": self.autofill,
            "tokens": sorted(self.tokens),
            "elements": [e.to_dict() for e in sorted(self.elements.values(), key=lambda e: e.priority)],
        }


@dataclass
class Transition:
    id: str
    src: str
    dst: str
    key: str
    action: str
    label: str
    kind: str
    count: int = 1
    step: int = 0
    inferred: bool = False  # not performed: predicted from the same nav element on another screen
    timings: list[dict] = field(default_factory=list)  # perf.Timing per traversal (load_ms, frames, jank…)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.src,
            "to": self.dst,
            "key": self.key,
            "action": self.action,
            "label": self.label,
            "kind": self.kind,
            "count": self.count,
            "step": self.step,
            "inferred": self.inferred,
            "load_ms": round(statistics.median(loads))
            if (loads := [t["load_ms"] for t in self.timings if t.get("load_ms") is not None])
            else None,
            "timings": self.timings,
        }


def selector_for(info: ElementInfo) -> dict:
    """How automation tools should find this element again, best first."""
    sel: dict = {}
    if info.rid:
        sel["id"] = info.rid
    if info.text.strip():
        sel["text"] = info.text.strip()
    elif info.desc.strip():
        sel["desc"] = info.desc.strip()
    x1, y1, x2, y2 = info.bounds
    sel["point"] = [(x1 + x2) // 2, (y1 + y2) // 2]
    return sel


class AppMap:
    def __init__(self, run: dict):
        self.run = run
        self.screens: dict[str, Screen] = {}
        self.transitions: dict[tuple[str, str, str], Transition] = {}
        self.events: list[dict] = []
        self.perf: dict = {"startup": []}  # am start -W timings of every (cold) launch
        self._next_el = 0

    # ── screens ──────────────────────────────────────────────────────────────
    def new_screen(self, obs: Observation, step: int, kind: str = "app") -> Screen:
        sid = (
            f"s{len([s for s in self.screens.values() if s.kind == 'app']) + 1:03d}"
            if kind == "app"
            else None
        )
        if kind == "external":
            sid = f"x:{obs.package}"
        elif kind == "crash":
            sid = "crash"
        screen = Screen(
            id=sid,
            kind=kind,
            signature=obs.signature,
            tokens=obs.tokens,
            fixed_tokens=obs.fixed_tokens,
            layout=obs.layout,
            package=obs.package,
            activity=obs.activity,
            title=obs.title if kind == "app" else (obs.package or kind),
            patterns=list(obs.patterns) if kind == "app" else [],
            width=obs.width,
            height=obs.height,
            first_step=step,
            signatures={obs.signature},
        )
        if kind == "app":
            self.merge_elements(screen, obs, scroll_depth=0)
        self.screens[sid] = screen
        return screen

    def merge_elements(self, screen: Screen, obs: Observation, scroll_depth: int) -> int:
        """Add elements not seen before on this screen; returns how many were new."""
        added = 0
        for info in obs.elements:
            if info.key in screen.elements:
                continue
            if info.kind == "input":
                continue  # inputs are filled on arrival, not explored as actions
            self._next_el += 1
            el = Element(id=f"e{self._next_el}", info=info, scroll_depth=scroll_depth)
            if info.blocked:
                el.status, el.note = "blocked", "matches blocked_text"
            screen.elements[info.key] = el
            added += 1
        for p in obs.patterns:
            if p not in screen.patterns and p not in ("empty",):
                screen.patterns.append(p)
        return added

    def apply_list_cap(self, screen: Screen, max_items: int, hard_cap: int = 25) -> None:
        """Learn list patterns: once the first items of a list all lead to the same kind of screen
        (a data list such as a feed), skip the rest. Lists whose items go to different screens
        (menus, settings) keep being explored, up to `hard_cap` items."""
        by_group: dict[str, list[Element]] = {}
        for el in sorted(screen.elements.values(), key=lambda e: e.priority):
            if el.info.kind == "list_item" and el.info.group:
                by_group.setdefault(el.info.group, []).append(el)
        for items in by_group.values():
            pending = [e for e in items if e.status == "pending"]
            if not pending:
                continue
            done = [e for e in items if e.status == "done"]
            reason = None
            if len(done) >= max_items and self._same_outcome(done[:max_items]):
                target = done[0].target or "the same screen"
                reason = f"list pattern: first {max_items} items all lead to {target}"
            elif len(done) + len([e for e in items if e.status == "failed"]) >= hard_cap:
                reason = f"list pattern: explored {hard_cap} items"
            if reason:
                for e in pending:
                    e.status, e.note = "skipped", reason

    def _same_outcome(self, els: list[Element]) -> bool:
        targets = [e.target for e in els]
        if all(t is None for t in targets):
            return True  # none of them navigated anywhere
        if any(t is None for t in targets):
            return False
        base = {self.screens[t].variant_of or t for t in targets}
        if len(base) == 1:
            return True
        first = self.screens[targets[0]].layout
        return all(weighted_jaccard(first, self.screens[t].layout) >= LAYOUT_VARIANT for t in targets[1:])

    def mark_variant(self, screen: Screen, src: Screen, el: Element) -> None:
        """A screen opened from a list row is a variant of what its sibling rows opened,
        when the layouts match (e.g. the detail page for article 2 vs article 1)."""
        if el.info.kind != "list_item" or not el.info.group:
            return
        for sib in src.elements.values():
            if sib is el or sib.info.group != el.info.group or not sib.target:
                continue
            other = self.screens.get(sib.target)
            if other is None or other is screen or other.kind != "app":
                continue
            if weighted_jaccard(other.layout, screen.layout) >= LAYOUT_VARIANT:
                screen.variant_of = other.variant_of or other.id
                return

    def infer_global_nav(self, screen: Screen) -> list[Transition]:
        """Bottom-nav and tab items behave the same on every screen that shows them: they go to
        the same destination, or (like a theme switch in the bar) keep you where you are."""
        known: dict[str, tuple[str | None, str]] = {}
        for other in self.screens.values():
            if other is screen or other.kind != "app":
                continue
            for e in other.elements.values():
                if e.info.kind not in ("nav", "tab") or e.status != "done" or e.effect == "inferred":
                    continue
                if e.target or e.effect == "same_screen":
                    known.setdefault(e.key, (e.target, other.id))
        added = []
        for e in screen.elements.values():
            if e.status != "pending" or e.info.kind not in ("nav", "tab"):
                continue
            if e.info.selected:
                e.status, e.effect, e.note = "done", "same_screen", "already selected"
                continue
            if e.key not in known:
                continue
            target, via = known[e.key]
            if target is None or target == screen.id:
                e.status, e.effect, e.note = "done", "same_screen", f"no navigation (as on {via})"
                continue
            e.status, e.effect, e.note, e.target = "done", "inferred", f"same nav item as on {via}", target
            if target in self.screens:
                added.append(self.add_transition(screen, self.screens[target], e, 0, inferred=True))
        return added

    def block_everywhere(self, key: str, note: str) -> None:
        """Never perform this element again, on any screen (e.g. it took us out of the app)."""
        for s in self.screens.values():
            e = s.elements.get(key)
            if e is not None and e.status == "pending":
                e.status, e.note = "blocked", note

    def add_back(self, screen: Screen) -> None:
        if "SYS|back" not in screen.elements:
            info = ElementInfo(
                key="SYS|back",
                kind="back",
                action="back",
                label="Back (system)",
                cls="",
                rid="",
                text="",
                desc="",
                hint="",
                bounds=(0, 0, 0, 0),
            )
            self._next_el += 1
            screen.elements["SYS|back"] = Element(id=f"e{self._next_el}", info=info)

    def add_transition(
        self, src: Screen, dst: Screen, el: Element, step: int, inferred: bool = False
    ) -> Transition:
        k = (src.id, dst.id, el.key)
        if k in self.transitions:
            t = self.transitions[k]
            if not inferred:
                if t.inferred:
                    t.inferred, t.step = False, step  # now confirmed by actually doing it
                else:
                    t.count += 1
            return t
        t = Transition(
            id=f"t{len(self.transitions) + 1}",
            src=src.id,
            dst=dst.id,
            key=el.key,
            action=el.info.action,
            label=el.info.label,
            kind=el.info.kind,
            step=step,
            inferred=inferred,
            count=0 if inferred else 1,
        )
        self.transitions[k] = t
        return t

    def out_edges(self, sid: str) -> list[Transition]:
        return [t for t in self.transitions.values() if t.src == sid]

    # ── serialization ────────────────────────────────────────────────────────
    def stats(self) -> dict:
        app_screens = [s for s in self.screens.values() if s.kind == "app"]
        declared = set(self.run.get("app", {}).get("activities") or [])
        visited = {s.activity for s in app_screens if s.activity}
        statuses: dict[str, int] = {}
        for s in app_screens:
            for e in s.elements.values():
                statuses[e.status] = statuses.get(e.status, 0) + 1
        return {
            "screens": len(app_screens),
            "external": len([s for s in self.screens.values() if s.kind == "external"]),
            "transitions": len(self.transitions),
            "max_depth": max((s.depth for s in app_screens), default=0),
            "activities_visited": sorted(visited),
            "activities_declared": len(declared),
            "activity_coverage": round(len(visited & declared) / len(declared), 3) if declared else None,
            "crashes": len([e for e in self.events if e["type"] == "crash"]),
            "elements": statuses,
        }

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "run": self.run,
            "screens": [s.to_dict() for s in self.screens.values()],
            "transitions": [t.to_dict() for t in self.transitions.values()],
            "events": self.events,
            "perf": self.perf,
            "stats": self.stats(),
        }

    def save(self, path: Path) -> None:
        write_json_atomic(path, self.to_dict())


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def load_map(run_dir: str | Path) -> dict:
    return json.loads((Path(run_dir) / "map.json").read_text())
