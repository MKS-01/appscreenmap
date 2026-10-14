"""Turn a uiautomator hierarchy dump into elements, a screen signature, a title and UI patterns."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
_DIGITS_RE = re.compile(r"\d")
_SPACE_RE = re.compile(r"\s+")

PERMISSION_PACKAGES = ("com.android.permissioncontroller", "com.google.android.permissioncontroller")
PERMISSION_ALLOW_IDS = (
    "permission_allow_foreground_only_button",
    "permission_allow_button",
    "permission_allow_one_time_button",
    "permission_allow_all_button",
)
UP_LABELS = {"navigate up", "back", "up", "close", "go back"}

# Lower value = explored earlier.
KIND_PRIORITY = {
    "nav": 0,
    "tab": 1,
    "button": 2,
    "scroll": 3,
    "list_item": 4,
    "toggle": 5,
    "long_click": 6,
    "up": 8,
    "back": 9,
}


@dataclass(eq=False)
class Node:
    cls: str
    rid: str
    text: str
    desc: str
    hint: str
    package: str
    bounds: tuple[int, int, int, int]
    clickable: bool
    long_clickable: bool
    scrollable: bool
    checkable: bool
    checked: bool
    enabled: bool
    focusable: bool
    password: bool
    selected: bool
    parent: Node | None = None
    children: list[Node] = field(default_factory=list)
    depth: int = 0
    repeat_group: str | None = None  # set on the root of a repeated list item
    in_repeat: str | None = None  # set on every node inside a repeated list item

    @property
    def short_cls(self) -> str:
        return self.cls.rsplit(".", 1)[-1]

    @property
    def short_rid(self) -> str:
        return self.rid.split("/", 1)[-1] if self.rid else ""

    @property
    def width(self) -> int:
        return max(0, self.bounds[2] - self.bounds[0])

    @property
    def height(self) -> int:
        return max(0, self.bounds[3] - self.bounds[1])

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[int, int]:
        return (self.bounds[0] + self.bounds[2]) // 2, (self.bounds[1] + self.bounds[3]) // 2

    @property
    def is_input(self) -> bool:
        return "EditText" in self.cls or "AutoCompleteTextView" in self.cls

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class ElementInfo:
    """An actionable element seen on one observation."""

    key: str
    kind: str
    action: str  # click | long_click | scroll | input
    label: str
    cls: str
    rid: str
    text: str
    desc: str
    hint: str
    bounds: tuple[int, int, int, int]
    group: str | None = None
    password: bool = False
    checked: bool | None = None
    selected: bool = False
    blocked: bool = False
    direction: str | None = None  # for scroll: "up" (reveal content below) or "left"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "kind": self.kind,
            "action": self.action,
            "label": self.label,
            "class": self.cls,
            "rid": self.rid,
            "text": self.text,
            "desc": self.desc,
            "hint": self.hint,
            "bounds": list(self.bounds),
            "group": self.group,
            "password": self.password,
            "checked": self.checked,
            "selected": self.selected,
            "direction": self.direction,
        }


@dataclass
class Observation:
    xml: str
    root: Node
    package: str | None
    activity: str | None
    width: int
    height: int
    tokens: frozenset[str]
    fixed_tokens: frozenset[str]  # tokens outside scroll containers / WebViews
    signature: str
    layout: Counter  # depth-aware node counts: compares layouts even when every node is a plain View
    elements: list[ElementInfo]
    patterns: list[str]
    title: str

    @property
    def activity_short(self) -> str:
        return (self.activity or "?").rsplit(".", 1)[-1]

    def element(self, key: str) -> ElementInfo | None:
        return next((e for e in self.elements if e.key == key), None)

    def find_rid(self, *suffixes: str) -> Node | None:
        for n in self.root.walk():
            if n.rid and any(n.rid.endswith("/" + s) for s in suffixes):
                return n
        return None

    def texts(self) -> list[str]:
        return [n.text for n in self.root.walk() if n.text]


# ── parsing ──────────────────────────────────────────────────────────────────


def _b(attr: dict, name: str) -> bool:
    return attr.get(name) == "true"


def parse_hierarchy(xml: str) -> Node:
    tree = ET.fromstring(xml.encode("utf-8"))

    def build(el: ET.Element, parent: Node | None, depth: int) -> Node:
        a = el.attrib
        m = _BOUNDS_RE.match(a.get("bounds", ""))
        bounds = tuple(int(v) for v in m.groups()) if m else (0, 0, 0, 0)
        node = Node(
            cls=a.get("class", ""),
            rid=a.get("resource-id", ""),
            text=a.get("text", "") or "",
            desc=a.get("content-desc", "") or "",
            hint=a.get("hint", "") or "",
            package=a.get("package", ""),
            bounds=bounds,
            clickable=_b(a, "clickable"),
            long_clickable=_b(a, "long-clickable"),
            scrollable=_b(a, "scrollable"),
            checkable=_b(a, "checkable"),
            checked=_b(a, "checked"),
            enabled=a.get("enabled", "true") == "true",
            focusable=_b(a, "focusable"),
            password=_b(a, "password"),
            selected=_b(a, "selected"),
            parent=parent,
            depth=depth,
        )
        node.children = [build(c, node, depth + 1) for c in el if c.tag == "node"]
        return node

    nodes = [c for c in tree if c.tag == "node"]
    if len(nodes) == 1:
        return build(nodes[0], None, 0)
    # Several windows (rare): wrap them in a synthetic root.
    root = Node("hierarchy", "", "", "", "", "", (0, 0, 0, 0), *([False] * 9))
    root.children = [build(c, root, 1) for c in nodes]
    return root


def normalize_text(s: str, limit: int = 40) -> str:
    s = _SPACE_RE.sub(" ", _DIGITS_RE.sub("#", s.strip().lower()))
    return s[:limit]


def _shape(node: Node, depth: int = 0) -> str:
    """Structural fingerprint of a subtree (class + id skeleton), ignoring text and size."""
    if depth > 4:
        return node.short_cls
    inner = ",".join(_shape(c, depth + 1) for c in node.children)
    return f"{node.short_cls}#{node.short_rid}({inner})"


def _mark_repeats(root: Node) -> None:
    """Find list items: sibling subtrees with the same shape (2+ in a scroller, else 3+)."""
    for parent in root.walk():
        if len(parent.children) < 2:
            continue
        in_scroller = parent.scrollable or any(a.scrollable for a in _ancestors(parent, 2))
        # Leaf siblings only count as rows inside real list widgets; Compose flattens a LazyColumn
        # into leaf Text/Image siblings that are headers, buttons and labels, not list items.
        list_widget = any(t in parent.cls for t in ("ListView", "RecyclerView", "GridView"))
        by_shape: dict[str, list[Node]] = defaultdict(list)
        for c in parent.children:
            if c.children or (list_widget and (c.text or c.desc)):
                by_shape[_shape(c)].append(c)
        for shape, items in by_shape.items():
            if len(items) >= (2 if in_scroller else 3) and not all(i.is_input for i in items):
                gid = f"{parent.short_rid or parent.short_cls}:{hashlib.sha1(shape.encode()).hexdigest()[:6]}"
                _mark_group(items, gid)
        # Grids and keypads: 6+ same-class, same-size siblings even when their ids differ.
        if len(parent.children) >= 6:
            by_size: dict[tuple, list[Node]] = defaultdict(list)
            for c in parent.children:
                if not c.in_repeat and not c.is_input and c.area > 0 and (c.clickable or c.text or c.desc):
                    by_size[(c.short_cls, c.width // 8, c.height // 8)].append(c)
            for (cls, w, h), items in by_size.items():
                if len(items) >= 6:
                    _mark_group(items, f"{parent.short_rid or parent.short_cls}:grid-{cls}-{w}x{h}")


def _mark_group(items: list[Node], gid: str) -> None:
    for item in items:
        if item.in_repeat:
            continue
        item.repeat_group = gid
        for n in item.walk():
            n.in_repeat = n.in_repeat or gid


def _ancestors(node: Node, limit: int = 99):
    p, i = node.parent, 0
    while p is not None and i < limit:
        yield p
        p, i = p.parent, i + 1


def _label(node: Node) -> str:
    for v in (node.text, node.desc, node.hint):
        if v and v.strip():
            return _SPACE_RE.sub(" ", v.strip())[:80]
    parts: list[str] = []
    for d in node.walk():
        if d is node:
            continue
        v = d.text or d.desc
        if v and v.strip() and v.strip() not in parts:
            parts.append(_SPACE_RE.sub(" ", v.strip()))
        if len(parts) >= 3:
            break
    if parts:
        return " / ".join(parts)[:80]
    return node.short_rid or node.short_cls


# ── analysis ─────────────────────────────────────────────────────────────────


def analyze(
    xml: str,
    package: str | None,
    activity: str | None,
    width: int,
    height: int,
    long_click: bool = False,
    explore_toggles: bool = True,
    is_blocked=lambda label: False,
) -> Observation:
    root = parse_hierarchy(xml)
    _mark_repeats(root)
    nodes = list(root.walk())
    if package is None:
        counts = Counter(n.package for n in nodes if n.package)
        package = counts.most_common(1)[0][0] if counts else None

    tokens: set[str] = set()
    fixed: set[str] = set()  # tokens of the part that doesn't scroll (title, toolbar, nav)
    for n in nodes:
        scrolling = any(a.scrollable or "WebView" in a.cls for a in _ancestors(n))
        tok = f"S:{n.short_cls}|{n.short_rid}"
        tokens.add(tok)
        if not scrolling:
            fixed.add(tok)
        if n.in_repeat or n.is_input:
            continue
        for prefix, value in (("T:", n.text), ("D:", n.desc)):
            if value.strip():
                t = prefix + normalize_text(value)
                tokens.add(t)
                if not scrolling:
                    fixed.add(t)
    tokens.discard("S:|")
    act = (activity or "").rsplit(".", 1)[-1]
    sig = hashlib.sha1((f"{package}|{act}\n" + "\n".join(sorted(tokens))).encode()).hexdigest()[:12]

    elements = _elements(nodes, width, height, long_click, explore_toggles, is_blocked)
    return Observation(
        xml=xml,
        root=root,
        package=package,
        activity=activity,
        width=width,
        height=height,
        tokens=frozenset(tokens),
        fixed_tokens=frozenset(fixed - {"S:|"}),
        layout=layout_fingerprint(nodes),
        signature=sig,
        elements=elements,
        patterns=_patterns(root, nodes, elements, width, height),
        title=_title(nodes, height, activity),
    )


def _visible(n: Node, width: int, height: int) -> bool:
    x1, y1, x2, y2 = n.bounds
    return n.area > 0 and x2 > 0 and y2 > 0 and x1 < width and y1 < height and n.width >= 8 and n.height >= 8


def _row_siblings(n: Node) -> list[Node]:
    """Clickable siblings sharing roughly the same vertical centre (tab bars / bottom navs)."""
    if n.parent is None:
        return []
    cy = n.center[1]
    return [
        s
        for s in n.parent.children
        if (s.clickable or s.checkable) and abs(s.center[1] - cy) <= max(12, n.height // 4)
    ]


def _kind(n: Node, width: int, height: int) -> str:
    cls = n.cls
    if n.checkable and any(t in cls for t in ("Switch", "CheckBox", "RadioButton", "ToggleButton", "Chip")):
        return "toggle"
    label = (n.desc or n.text).strip().lower()
    if label in UP_LABELS and n.center[1] < height * 0.15:
        return "up"
    if "Tab" in cls or (n.parent and "Tab" in n.parent.cls):
        return "tab"
    row = _row_siblings(n)
    if len(row) >= 3:
        if n.bounds[1] > height * 0.82:
            return "nav"
        if n.center[1] < height * 0.4 and any(s.selected for s in row):
            return "tab"
    if "NavigationBarItemView" in cls or "BottomNavigationItemView" in cls:
        return "nav"
    if n.in_repeat:
        return "list_item"
    if n.checkable:
        return "toggle"
    return "button"


def _elements(
    nodes: list[Node], width: int, height: int, long_click: bool, explore_toggles: bool, is_blocked
) -> list[ElementInfo]:
    screen_area = width * height
    raw: list[tuple[Node, str, str]] = []  # (node, kind, action)
    for n in nodes:
        if not n.enabled or not _visible(n, width, height):
            continue
        if n.is_input:
            raw.append((n, "input", "input"))
            continue
        if n.scrollable and n.area < screen_area * 1.01:
            raw.append((n, "scroll", "scroll"))
        # ListView/GridView rows are often not flagged clickable (the list handles the tap).
        implicit = (
            n.parent is not None
            and any(t in n.parent.cls for t in ("ListView", "GridView"))
            and not any(d.clickable for d in n.walk())
        )
        if (n.clickable or n.checkable or implicit) and n.area < screen_area * 0.9:
            kind = _kind(n, width, height)
            if kind == "toggle" and not explore_toggles:
                continue
            raw.append((n, kind, "click"))
        if long_click and n.long_clickable and n.area < screen_area * 0.9:
            raw.append((n, "long_click", "long_click"))

    rid_counts = Counter(n.rid for n, _, _ in raw if n.rid)
    seen_keys: set[str] = set()
    out: list[ElementInfo] = []
    for n, kind, action in raw:
        label = _label(n)
        group = n.in_repeat
        if group and not n.repeat_group:
            # A control nested inside list items (e.g. each card's "More" button) is its own group.
            group = f"{group}/{n.short_cls}#{n.short_rid}"
        if action == "scroll":
            x1, y1, x2, y2 = (v // 40 for v in n.bounds)  # by position: a scroller's content changes
            key = f"scroll|{n.short_cls}|{n.rid}|{x1},{y1},{x2},{y2}"
        elif kind == "list_item" and group:
            key = f"L|{group}|{normalize_text(label, 60)}"
        elif n.rid and rid_counts[n.rid] == 1:
            key = f"{action}|{n.short_cls}|{n.rid}"
        else:
            ident = normalize_text(label, 60) if label else f"@{n.center[0] // 40},{n.center[1] // 40}"
            key = f"{action}|{n.short_cls}|{n.rid}|{ident}"
        if key in seen_keys:
            # Distinct nodes whose normalized labels collide ("15 MIN" / "25 MIN", "Story 1" / "Story 2").
            ordinal = 2
            while f"{key}#{ordinal}" in seen_keys:
                ordinal += 1
            key = f"{key}#{ordinal}"
        seen_keys.add(key)
        blocked = action != "scroll" and kind != "input" and is_blocked(label)
        el = ElementInfo(
            key=key,
            kind=kind,
            action=action,
            label=label,
            cls=n.cls,
            rid=n.rid,
            text=n.text,
            desc=n.desc,
            hint=n.hint,
            bounds=n.bounds,
            group=group if kind == "list_item" else None,
            password=n.password,
            checked=n.checked if n.checkable else None,
            selected=n.selected,
            blocked=blocked,
        )
        if action == "scroll":
            el.direction = "left" if (n.width > n.height * 1.6 and n.height < height * 0.35) else "up"
            el.label = f"Scroll {n.short_rid or n.short_cls}"
        out.append(el)
    return out


def _patterns(
    root: Node, nodes: list[Node], elements: list[ElementInfo], width: int, height: int
) -> list[str]:
    p: list[str] = []
    kinds = Counter(e.kind for e in elements)
    if any(n.repeat_group for n in nodes):
        p.append("list")
    if kinds["tab"] >= 2:
        p.append("tabs")
    if kinds["nav"] >= 3:
        p.append("bottom_nav")
    inputs = [e for e in elements if e.kind == "input"]
    if inputs:
        p.append("form")
        if any(e.password for e in inputs):
            p.append("login")
    content = [n for n in nodes if n.depth <= 3 and n.area > 0]
    if root.bounds != (0, 0, 0, 0) and content:
        top = max(content, key=lambda n: n.area)
        if top.area < width * height * 0.8 or any(
            "Dialog" in n.cls or n.rid.endswith("/alertTitle") for n in nodes
        ):
            p.append("dialog")
    if any("DrawerLayout" in n.cls for n in nodes):
        p.append("drawer")
    if any("WebView" in n.cls for n in nodes):
        p.append("webview")
    if kinds["scroll"]:
        p.append("scrollable")
    actionable = [e for e in elements if e.kind not in ("scroll", "input")]
    if not actionable:
        p.append("empty")
    return p


def _title(nodes: list[Node], height: int, activity: str | None) -> str:
    for n in nodes:
        r = n.short_rid.lower()
        if n.text.strip() and ("title" in r or "toolbar" in r or "header" in r) and not n.in_repeat:
            return n.text.strip()[:60]
    for n in nodes:
        if n.rid.endswith("/alertTitle") and n.text.strip():
            return n.text.strip()[:60]
    # First non-button text in the top fifth of the screen (below the status bar).
    for n in nodes:
        if (
            n.text.strip()
            and not n.clickable
            and not n.in_repeat
            and not n.is_input
            and height * 0.03 < n.bounds[1] < height * 0.2
            and len(n.text.strip()) <= 60
        ):
            return n.text.strip()
    for n in nodes:
        if n.text.strip() and not n.in_repeat and not n.is_input and len(n.text.strip()) <= 40:
            return n.text.strip()
    return (activity or "Screen").rsplit(".", 1)[-1]


def layout_fingerprint(nodes: list[Node]) -> Counter:
    """Count of (depth, class, id) outside list rows, plus one token per list group."""
    c: Counter = Counter()
    for n in nodes:
        if n.in_repeat:
            if n.repeat_group:
                c[f"R|{n.depth}|{n.repeat_group.split(':', 1)[0]}"] = 1
            continue
        c[f"{n.depth}|{n.short_cls}|{n.short_rid}"] += 1
    return c


def weighted_jaccard(a: Counter, b: Counter) -> float:
    keys = a.keys() | b.keys()
    hi = sum(max(a[k], b[k]) for k in keys)
    return sum(min(a[k], b[k]) for k in keys) / hi if hi else 1.0


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def is_permission_dialog(obs: Observation) -> bool:
    return obs.package in PERMISSION_PACKAGES or obs.find_rid(*PERMISSION_ALLOW_IDS) is not None


def is_crash_dialog(obs: Observation) -> bool:
    if obs.find_rid("aerr_close", "aerr_restart", "aerr_wait", "aerr_app_info") is not None:
        return True
    texts = " ".join(obs.texts()).lower()
    return obs.package == "android" and (
        "keeps stopping" in texts or "isn't responding" in texts or "has stopped" in texts
    )
