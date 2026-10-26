"""Turn a hand-driven session into a Maestro flow: touch events resolved against the screen they landed on.

Pure logic, no device: `TouchTracker` reads `getevent -lt` lines, `FlowRecorder` maps each gesture to the element
under it (from the latest UI hierarchy) and renders the YAML. The `record` command feeds both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from appscreenmap.core.analyzer import Node, parse_hierarchy

from .maestro import _q, _regex_literal

_EVENT_RE = re.compile(r"\[\s*([\d.]+)\]\s+(?:(\S+):\s+)?(EV_\w+)\s+(\w+)\s+(\w+)")
TAP_SLOP = 0.03  # a touch that moves less than this share of the screen is a tap
LONG_PRESS_S = 0.6
EDGE = 0.04  # a swipe that starts this close to the left or right edge is the back gesture
PASSWORD_VAR = "${ACCOUNT_PASSWORD}"


@dataclass(frozen=True)
class Gesture:
    t_down: float
    t_up: float
    start: tuple[int, int]  # raw device units
    end: tuple[int, int]


class TouchTracker:
    """Feed `getevent -lt` lines; a finished touch comes back as a Gesture."""

    def __init__(self) -> None:
        self.x = self.y = None
        self.down_t: float | None = None
        self.start: tuple[int, int] | None = None

    def feed(self, line: str) -> Gesture | None:
        m = _EVENT_RE.search(line)
        if not m:
            return None
        t, kind, code, value = float(m[1]), m[3], m[4], m[5]
        if kind == "EV_ABS" and code == "ABS_MT_POSITION_X":
            self.x = int(value, 16)
        elif kind == "EV_ABS" and code == "ABS_MT_POSITION_Y":
            self.y = int(value, 16)
        elif kind == "EV_ABS" and code == "ABS_MT_TRACKING_ID":
            if value.lower() == "ffffffff":
                return self._up(t)
            self.down_t, self.start = t, None
        elif kind == "EV_KEY" and code == "BTN_TOUCH":
            if value.upper() == "UP":
                return self._up(t)
            if self.down_t is None:
                self.down_t, self.start = t, None
        elif (
            kind == "EV_SYN"
            and self.down_t is not None
            and self.start is None
            and self.x is not None
            and self.y is not None
        ):
            self.start = (self.x, self.y)
        return None

    def _up(self, t: float) -> Gesture | None:
        if self.down_t is None or self.x is None or self.y is None:
            return None
        g = Gesture(self.down_t, t, self.start or (self.x, self.y), (self.x, self.y))
        self.down_t, self.start = None, None
        return g


class MultiTouch:
    """One tracker per input device: an emulator exposes several touch nodes and the touch lands on any of them."""

    def __init__(self) -> None:
        self.devices: dict[str, TouchTracker] = {}

    def feed(self, line: str) -> Gesture | None:
        m = _EVENT_RE.search(line)
        if not m:
            return None
        return self.devices.setdefault(m[2] or "", TouchTracker()).feed(line)


def _hit(node: Node, x: int, y: int) -> bool:
    l, t, r, b = node.bounds
    return l <= x < r and t <= y < b and node.area > 0


def selector_at(root: Node, x: int, y: int) -> tuple[dict, Node | None]:
    """The smallest named element under the point, as a selector the Maestro exporter understands."""
    hits = sorted((n for n in root.walk() if _hit(n, x, y)), key=lambda n: n.area)
    for n in hits:
        if n.rid and not n.rid.startswith("android:id/") and ":id/" not in n.rid:
            return {"id": n.rid}, n
        if n.desc:
            return {"desc": n.desc}, n
        if n.text:
            return {"text": n.text}, n
    # An unnamed tap target (an icon) hands its label up from a child or the nearest clickable ancestor.
    for n in hits:
        if n.clickable:
            for c in n.walk():
                if c.rid and ":id/" not in c.rid:
                    return {"id": c.rid}, n
                if c.desc or c.text:
                    return ({"desc": c.desc} if c.desc else {"text": c.text}), n
    return {"point": [x, y]}, hits[0] if hits else None


def _target(sel: dict, width: int, height: int) -> str:
    if sel.get("id"):
        return "{ id: " + _q(sel["id"]) + " }"
    if sel.get("desc"):
        return _q(_regex_literal(sel["desc"]))
    if sel.get("text"):
        return _q(_regex_literal(sel["text"]))
    x, y = sel["point"]
    return "{ point: " + _q(f"{round(100 * x / max(width, 1))}%,{round(100 * y / max(height, 1))}%") + " }"


def _is_field(n: Node) -> bool:
    """A text field: a real EditText, or (React Native) a tappable TextView that carries a hint."""
    return n.is_input or bool(n.hint and n.clickable)


def _inputs(root: Node) -> dict[str, Node]:
    out: dict[str, Node] = {}
    for i, n in enumerate(n for n in root.walk() if _is_field(n)):
        out[n.rid or n.desc or n.hint or f"#{i}"] = n
    return out


class FlowRecorder:
    """Collects the flow as gestures and screen snapshots arrive, in order."""

    def __init__(
        self, package: str, width: int, height: int, raw_max: tuple[int, int], clear_state: bool = False
    ):
        self.package, self.w, self.h = package, width, height
        self.raw_max = raw_max
        self.clear_state = clear_state
        self.lines: list[str] = []
        self.root: Node | None = None
        self.title = ""
        self._fields: dict[str, str] = {}

    def _px(self, p: tuple[int, int]) -> tuple[int, int]:
        return (
            round(p[0] * self.w / max(self.raw_max[0], 1)),
            round(p[1] * self.h / max(self.raw_max[1], 1)),
        )

    def on_snapshot(self, xml: str) -> None:
        """Record what was typed since the last look, and remember the screen for the next tap."""
        try:
            root = parse_hierarchy(xml)
        except Exception:  # noqa: BLE001  a half-written dump is skipped, the next one is fine
            return
        fields = _inputs(root)
        for key, node in fields.items():
            now, before = node.text, self._fields.get(key, "")
            placeholder = node.hint and now == node.hint
            if placeholder or now == before:
                continue
            if node.password or "password" in node.rid.lower():
                if before:
                    continue
                value = PASSWORD_VAR
            else:
                value = now
                if before and now.startswith(before):
                    value = now[len(before) :]
                elif before:
                    self.lines.append("- eraseText")
            while self.lines and self.lines[-1].startswith("- tapOn: { point"):
                self.lines.pop()  # taps on the on-screen keyboard resolve to bare points: the typing replaces them
            focus = "- tapOn: " + _target(
                {"id": node.rid} if node.rid else {"desc": node.desc or node.hint}, self.w, self.h
            )
            # Several fields can change between two looks; inputText goes to whichever is focused, so focus each one.
            if focus not in [x for x in self.lines[-1:]]:
                self.lines.append(focus)
            self.lines.append("- inputText: " + _q(value))
        self._fields = {k: ("" if (n.hint and n.text == n.hint) else n.text) for k, n in fields.items()}
        titles = [n.text for n in root.walk() if n.text and n.depth <= 8 and not _is_field(n)]
        if titles and titles[0] != self.title and self.root is not None:
            self.title = titles[0]
            self.lines.append(f"# screen: {self.title}")
        elif self.root is None and titles:
            self.title = titles[0]
        self.root = root

    def on_gesture(self, g: Gesture) -> None:
        if self.root is None:
            return
        sx, sy = self._px(g.start)
        ex, ey = self._px(g.end)
        moved = max(abs(ex - sx) / max(self.w, 1), abs(ey - sy) / max(self.h, 1))
        if moved >= TAP_SLOP:
            if sx / self.w < EDGE or sx / self.w > 1 - EDGE:
                self.lines.append("- back")
            else:
                a = f"{round(100 * sx / self.w)}%,{round(100 * sy / self.h)}%"
                b = f"{round(100 * ex / self.w)}%,{round(100 * ey / self.h)}%"
                self.lines.append(f"- swipe: {{ start: {_q(a)}, end: {_q(b)} }}")
            return
        sel, _ = selector_at(self.root, sx, sy)
        cmd = "longPressOn" if g.t_up - g.t_down >= LONG_PRESS_S else "tapOn"
        self.lines.append(f"- {cmd}: " + _target(sel, self.w, self.h))

    def render(self) -> str:
        head = [
            "# Recorded with `appscreenmap record`: hand-driven taps resolved to ids and labels.",
            f"appId: {self.package}",
            "---",
            "- launchApp:",
            "    stopApp: true",
        ]
        if self.clear_state:
            head.append("    clearState: true")
        body = "\n".join(self.lines)
        if PASSWORD_VAR in body:
            head.insert(1, "# Needs: maestro test -e ACCOUNT_PASSWORD=…")
        return "\n".join(head + self.lines) + "\n"
