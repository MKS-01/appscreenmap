"""WCAG 2.2 checks that need the whole crawl: cross-screen consistency, flows, device facts.

The web viewer runs per-screen Accessibility-Scanner-style checks in the browser (web/src/a11y.ts:
missing labels, 48 dp targets, contrast, …). This module adds what only a crawl can see and maps
every finding to a WCAG 2.2 success criterion. Output: `<run>/a11y.json` (see docs/MAP_SCHEMA.md).

Issue keys use the viewer's format, `<screen>::<rule>::<rid|class>::<label>::<x>,<y>`, so triage
decisions stored in notes.json (`a11y`) apply to both.

Automated results are evidence for a person to confirm. They are not a conformance claim.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .analyzer import Node, normalize_text, parse_hierarchy
from .model import load_map, write_json_atomic

A11Y_SCHEMA = 1


@dataclass(frozen=True)
class Rule:
    sc: str  # WCAG success criterion number
    name: str  # criterion name
    level: str  # A | AA | AAA
    kind: str  # "automated" (detected) | "review" (flagged for a person to check)
    severity: str  # error | warning | info
    why: str
    fix: str
    # Set when WCAG2ICT / EN 301 549 don't apply the criterion to a single native app as written.
    native_note: str = ""


RULES: dict[str, Rule] = {
    "target-size-min": Rule(
        "2.5.8",
        "Target Size (Minimum)",
        "AA",
        "automated",
        "error",
        "A tappable target is smaller than 24×24 dp and too close to another target "
        "(the 24 dp spacing circles overlap).",
        "Make the target at least 24×24 dp (48×48 dp is Android's guideline), or space targets so "
        "24 dp circles around each don't overlap. Compose: Modifier.minimumInteractiveComponentSize().",
    ),
    "label-in-name": Rule(
        "2.5.3",
        "Label in Name",
        "A",
        "automated",
        "warning",
        "The control shows text, but its accessible name (content description) doesn't contain it. "
        "Voice-control users say what they see, and it won't match.",
        "Start the content description with the visible text, or remove it so the visible text is used.",
    ),
    "not-focusable": Rule(
        "2.1.1",
        "Keyboard",
        "A",
        "automated",
        "warning",
        "The control is clickable but not focusable, so keyboard and switch-access users can't reach it.",
        "Make it focusable (android:focusable / Compose clickable or focusable modifiers).",
    ),
    "no-role": Rule(
        "4.1.2",
        "Name, Role, Value",
        "A",
        "automated",
        "info",
        "A clickable generic View exposes no role, so TalkBack doesn't say it's a button, tab, or switch.",
        "Use a real widget, or set the role: Modifier.semantics { role = Role.Button } / "
        "AccessibilityNodeInfo.setClassName.",
    ),
    "screen-title": Rule(
        "2.4.2",
        "Page Titled",
        "A",
        "review",
        "info",
        "No title could be found for this screen, so a screen-reader user may not know where they are.",
        "Give each screen a title: activity title, toolbar title, or accessibilityPaneTitle / "
        "Modifier.semantics { paneTitle = … } for fragments and Compose destinations.",
    ),
    "nav-inconsistent": Rule(
        "3.2.3",
        "Consistent Navigation",
        "AA",
        "automated",
        "warning",
        "The bottom navigation differs in order or content between screens.",
        "Keep repeated navigation in the same relative order on every screen.",
        native_note=(
            "Written for sets of web pages; WCAG2ICT and EN 301 549 don't require it for a single native "
            "app, so treat it as strong best practice there."
        ),
    ),
    "identification-inconsistent": Rule(
        "3.2.4",
        "Consistent Identification",
        "AA",
        "automated",
        "warning",
        "The same control (same resource id) is labelled differently on different screens.",
        "Use the same label for the same function everywhere.",
        native_note=(
            "Written for sets of web pages; WCAG2ICT and EN 301 549 don't require it for a single native "
            "app, so treat it as strong best practice there."
        ),
    ),
    "help-inconsistent": Rule(
        "3.2.6",
        "Consistent Help",
        "A",
        "automated",
        "warning",
        "A help/support/contact entry appears on several screens, but not in the same relative place.",
        "Put repeated help mechanisms in the same relative order on every screen.",
        native_note=(
            "Written for sets of web pages; WCAG2ICT and EN 301 549 don't require it for a single native "
            "app, so treat it as strong best practice there."
        ),
    ),
    "redundant-entry": Rule(
        "3.3.7",
        "Redundant Entry",
        "A",
        "review",
        "warning",
        "The same information was typed on more than one screen of one flow.",
        "Auto-fill information the user already gave, or let them select it.",
    ),
    "auth-cognitive": Rule(
        "3.3.8",
        "Accessible Authentication (Minimum)",
        "AA",
        "review",
        "warning",
        "This screen asks for a password, code, or puzzle. Authentication must not depend on a "
        "cognitive test unless paste, password managers, or another method are supported.",
        "Allow paste and autofill (autofillHints password/username/oneTimeCode), offer passkeys or "
        "email links, and avoid text CAPTCHAs.",
    ),
    "dragging": Rule(
        "2.5.7",
        "Dragging Movements",
        "AA",
        "review",
        "warning",
        "A slider, drag handle, or swipe-only control needs a single-tap alternative.",
        "Add buttons (e.g. +/−, move up/down) or accessibility custom actions for anything done by dragging.",
    ),
    "focus-obscured": Rule(
        "2.4.11",
        "Focus Not Obscured (Minimum)",
        "AA",
        "automated",
        "warning",
        "A focusable control sits completely under a sticky bar or floating button, so it is hidden "
        "when it gets focus.",
        "Add bottom padding/insets to scrolling content equal to the sticky bar's height, or scroll "
        "focused items into the visible area.",
    ),
    "orientation-locked": Rule(
        "1.3.4",
        "Orientation",
        "AA",
        "automated",
        "warning",
        "The activity is locked to one orientation in the manifest.",
        "Remove android:screenOrientation unless an orientation is essential (e.g. a piano app).",
    ),
    "text-truncated": Rule(
        "1.4.4",
        "Resize Text",
        "AA",
        "automated",
        "warning",
        "Text is cut off with an ellipsis. At larger font sizes this usually means lost content.",
        "Let text wrap (no maxLines/ellipsize on important text), use sp, and test at 200% font scale.",
    ),
    "change-on-input": Rule(
        "3.2.2",
        "On Input",
        "A",
        "automated",
        "error",
        "Typing into a field changed the screen without the user asking for it.",
        "Only navigate on an explicit action (a submit button), or warn users before it happens.",
    ),
    "image-alt": Rule(
        "1.1.1",
        "Non-text Content",
        "A",
        "review",
        "info",
        "A sizeable image has no text alternative. Fine if decorative; otherwise it needs one.",
        "Set contentDescription for meaningful images, and null / importantForAccessibility=no for decorative ones.",
    ),
}

_HELP_RE = re.compile(r"\b(help|support|contact( us)?|faq|chat with us|get help)\b", re.IGNORECASE)
_AUTH_RE = re.compile(
    r"\b(captcha|verification code|one[- ]time|otp|passcode|pin|security question)\b", re.IGNORECASE
)
_DRAG_HINT_RE = re.compile(r"\b(drag|reorder|swipe to|slide to)\b", re.IGNORECASE)


def _short(cls: str) -> str:
    return cls.rsplit(".", 1)[-1]


def _visible_text(n: Node) -> str:
    parts = [d.text.strip() for d in n.walk() if d.text.strip()]
    return " ".join(parts)


class _Collector:
    def __init__(self, data: dict, triage: dict):
        self.issues: list[dict] = []
        self.triage = triage
        self.screens = {s["id"]: s for s in data["screens"]}

    def add(
        self,
        rule_id: str,
        screen: str,
        label: str,
        detail: str,
        node: Node | None = None,
        bounds=None,
        rid: str = "",
        cls: str = "",
    ) -> None:
        r = RULES[rule_id]
        if node is not None:
            bounds, rid, cls = list(node.bounds), node.rid, node.cls
        b = bounds or [0, 0, 0, 0]
        key = f"{screen}::{rule_id}::{rid or _short(cls) or 'screen'}::{label}::{b[0]},{b[1]}"
        self.issues.append(
            {
                "key": key,
                "screen": screen,
                "rule": rule_id,
                "sc": r.sc,
                "level": r.level,
                "kind": r.kind,
                "severity": r.severity,
                "label": label,
                "detail": detail,
                "bounds": b,
                "rid": rid,
                "class": cls,
                "triage": self.triage.get(key, {}).get("status", "open"),
            }
        )


def _dp(data: dict) -> float:
    dev = data["run"].get("device", {})
    if dev.get("density"):
        return dev["density"] / 160
    return (dev.get("width") or 1080) / 411  # most phones are ~411 dp wide


def audit_run(run_dir: str | Path, write: bool = True) -> dict:
    run_dir = Path(run_dir)
    data = load_map(run_dir)
    triage = {}
    notes_file = run_dir / "notes.json"
    if notes_file.is_file():
        try:
            triage = json.loads(notes_file.read_text()).get("a11y", {})
        except (ValueError, OSError):
            triage = {}
    out = _Collector(data, triage)
    dp = _dp(data)
    pkg = data["run"].get("app", {}).get("package")
    app_screens = [s for s in data["screens"] if s["kind"] == "app"]
    trees: dict[str, Node] = {}
    for s in app_screens:
        if s.get("hierarchy") and (run_dir / s["hierarchy"]).is_file():
            trees[s["id"]] = parse_hierarchy((run_dir / s["hierarchy"]).read_text())

    for s in app_screens:
        if s["id"] in trees:
            _screen_checks(out, s, trees[s["id"]], dp, pkg)
    _cross_screen_checks(out, app_screens)
    _flow_checks(out, data, app_screens)
    _app_checks(out, data)
    uniq: dict[str, dict] = {}
    for i in out.issues:  # a screen reached by several paths reports once
        uniq.setdefault(i["key"], i)
    out.issues = list(uniq.values())

    by_sc = Counter(f"{i['sc']} {RULES[i['rule']].name}" for i in out.issues)
    report = {
        "schema": A11Y_SCHEMA,
        "run": data["run"]["id"],
        "standard": "WCAG 2.2",
        "dp_scale": round(dp, 3),
        "density_exact": bool(data["run"].get("device", {}).get("density")),
        "font_scale": data["run"].get("device", {}).get("font_scale"),
        "rules": {k: {**r.__dict__} for k, r in RULES.items()},
        "summary": {
            "issues": len(out.issues),
            "by_level": dict(Counter(i["level"] for i in out.issues)),
            "by_kind": dict(Counter(i["kind"] for i in out.issues)),
            "by_criterion": dict(sorted(by_sc.items())),
            "open": sum(1 for i in out.issues if i["triage"] == "open"),
        },
        "issues": sorted(out.issues, key=lambda i: (i["sc"], i["screen"], i["key"])),
    }
    if write:
        write_json_atomic(run_dir / "a11y.json", report)
    return report


# ── per screen (things the viewer's scanner rules don't cover) ───────────────


def _screen_checks(out: _Collector, s: dict, root: Node, dp: float, pkg: str | None) -> None:
    sid = s["id"]
    W, H = s.get("width") or 1080, s.get("height") or 2400
    nodes = [n for n in root.walk() if (not pkg or not n.package or n.package == pkg)]

    def on_screen(n: Node) -> bool:
        x1, y1, x2, y2 = n.bounds
        return n.area > 0 and x2 > 0 and y2 > 0 and x1 < W and y1 < H

    targets = [
        n
        for n in nodes
        if (n.clickable or n.checkable) and n.enabled and on_screen(n) and n.area < W * H * 0.9
    ]

    # 2.5.8: under 24×24 dp fails unless the spacing exception holds (24 dp circles don't overlap).
    r = 12 * dp
    centers = [(n, ((n.bounds[0] + n.bounds[2]) / 2, (n.bounds[1] + n.bounds[3]) / 2)) for n in targets]
    for n, (cx, cy) in centers:
        wdp, hdp = n.width / dp, n.height / dp
        if wdp >= 23.5 and hdp >= 23.5:
            continue
        if any(a.clickable and a.width / dp >= 24 and a.height / dp >= 24 for a in _ancestors(n)):
            continue  # the tappable parent provides the target
        close = []
        for m, (mx, my) in centers:
            if m is n or _related(n, m):
                continue
            small_m = m.width / dp < 23.5 or m.height / dp < 23.5
            # Circle around n vs the other target: its circle (if undersized) or its bounds.
            if small_m:
                hit = (cx - mx) ** 2 + (cy - my) ** 2 < (2 * r) ** 2
            else:
                nx = min(max(cx, m.bounds[0]), m.bounds[2])
                ny = min(max(cy, m.bounds[1]), m.bounds[3])
                hit = (cx - nx) ** 2 + (cy - ny) ** 2 < r**2
            if hit:
                close.append(m)
        if close:
            label = _name(n)
            out.add(
                "target-size-min",
                sid,
                label,
                f"{wdp:.0f}×{hdp:.0f} dp, within 24 dp spacing of {len(close)} other target(s)",
                n,
            )

    for n in targets:
        label = _name(n)
        # 2.5.3 Label in Name
        visible = _visible_text(n)
        if n.desc.strip() and visible and normalize_text(visible, 200) not in normalize_text(n.desc, 400):
            out.add(
                "label-in-name", sid, label, f"shows “{visible[:40]}” but is announced as “{n.desc[:40]}”", n
            )
        # 2.1.1 Keyboard
        if not n.focusable and not any(a.focusable and a.clickable for a in _ancestors(n)):
            out.add("not-focusable", sid, label, f"clickable {_short(n.cls)} is not focusable", n)
        # 4.1.2 role
        if n.cls == "android.view.View" and n.clickable and not n.checkable:
            out.add("no-role", sid, label, "clickable android.view.View with no role", n)
        # 2.5.7 dragging
        if "SeekBar" in n.cls or "Slider" in n.cls or _DRAG_HINT_RE.search(f"{n.desc} {n.text}"):
            out.add("dragging", sid, label, f"{_short(n.cls)} may need a non-drag alternative", n)

    for n in nodes:
        if "SeekBar" in n.cls and not (n.clickable or n.checkable) and on_screen(n):
            out.add("dragging", sid, _name(n), "slider: check there is a non-drag way to set the value", n)
        # 1.4.4: ellipsized text
        t = n.text.strip()
        if t.endswith(("…", "...")) and len(t) > 4 and on_screen(n):
            out.add("text-truncated", sid, t[:40], "text ends in an ellipsis", n)
        # 1.1.1: meaningful-sized image without alt text
        is_image = "ImageView" in n.cls or n.cls.endswith(".Image")
        big = n.width / dp >= 48 and n.height / dp >= 48
        if (
            is_image
            and big
            and not n.desc.strip()
            and not n.clickable
            and on_screen(n)
            and not any(a.desc for a in _ancestors(n))
        ):
            out.add(
                "image-alt",
                sid,
                n.short_rid or "image",
                f"{n.width / dp:.0f}×{n.height / dp:.0f} dp image",
                n,
            )

    # 2.4.11: focusable controls fully covered by a sticky bar (a bottom nav / FAB drawn later).
    bars = [n for n in nodes if _is_sticky_bar(n, W, H, dp)]
    for bar in bars:
        for n in targets:
            if n is bar or _related(n, bar) or not any(a.scrollable for a in _ancestors(n)):
                continue
            if _contains(bar.bounds, n.bounds):
                out.add(
                    "focus-obscured",
                    sid,
                    _name(n),
                    f"fully under {_name(bar)} at the bottom of the screen",
                    n,
                )

    # 3.3.8: authentication screens
    texts = " ".join(f"{n.text} {n.desc} {n.hint}" for n in nodes)
    if any(n.password for n in nodes) or _AUTH_RE.search(texts):
        what = "password field" if any(n.password for n in nodes) else _AUTH_RE.search(texts).group(0)
        out.add(
            "auth-cognitive", sid, s.get("title") or sid, f"{what}: check paste/autofill and alternatives"
        )

    # 2.4.2: no title found (title fell back to the activity name or is missing)
    act = (s.get("activity") or "").rsplit(".", 1)[-1]
    if not s.get("title") or s["title"] == act:
        out.add("screen-title", sid, s.get("title") or sid, "no visible screen title found")


def _ancestors(n: Node):
    p = n.parent
    while p is not None:
        yield p
        p = p.parent


def _related(a: Node, b: Node) -> bool:
    return a in _ancestors(b) or b in _ancestors(a)


def _contains(outer, inner) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _name(n: Node) -> str:
    """What a screen reader would announce: own desc/text, else descendants' text or descriptions."""
    label = (n.desc or n.text).strip() or _visible_text(n)
    if not label:
        label = " ".join(d.desc.strip() for d in n.walk() if d is not n and d.desc.strip())
    return (label or n.short_rid or _short(n.cls))[:60]


def _is_sticky_bar(n: Node, W: int, H: int, dp: float) -> bool:
    """A non-scrolling container pinned to the bottom with several tappable children, or a FAB."""
    if any(a.scrollable for a in _ancestors(n)):
        return False
    tappable = sum(1 for c in n.walk() if c is not n and c.clickable)
    bottom = n.bounds[3] >= H * 0.9 and n.bounds[1] > H * 0.7
    return bottom and (tappable >= 2 or "FloatingActionButton" in n.cls) and n.height / dp <= 160


# ── across screens ───────────────────────────────────────────────────────────


def _cross_screen_checks(out: _Collector, screens: list[dict]) -> None:
    # 3.2.3 Consistent Navigation: same nav items in the same order on every screen that has a nav bar.
    navs: dict[str, tuple[str, ...]] = {}
    for s in screens:
        items = sorted((e for e in s.get("elements", []) if e["kind"] == "nav"), key=lambda e: e["bounds"][0])
        if len(items) >= 3:
            navs[s["id"]] = tuple(normalize_text(e["label"]) for e in items)
    if len(navs) >= 2:
        common, _ = Counter(navs.values()).most_common(1)[0]
        for sid, seq in navs.items():
            # Only compare bars that are the same navigation (mostly the same items); a screen's own
            # control row at the bottom (e.g. player buttons) is not the app's navigation.
            if seq == common or len(set(seq) & set(common)) < len(common) / 2:
                continue
            missing = [x for x in common if x not in seq]
            if sorted(seq) == sorted(common):
                order = "different order"
            else:
                order = f"missing {missing}" if missing else "extra items"
            out.add("nav-inconsistent", sid, "bottom navigation", f"{order} vs. most screens: {list(common)}")

    # 3.2.4 Consistent Identification: same resource id, different label on different screens.
    by_rid: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for s in screens:
        for e in s.get("elements", []):
            if e.get("rid") and e["kind"] not in ("list_item", "scroll", "back") and e.get("label"):
                by_rid[e["rid"]][normalize_text(e["label"])].append(s["id"])
    for rid, labels in by_rid.items():
        if len(labels) > 1:
            first = min(labels.values(), key=lambda v: v[0])[0]
            out.add(
                "identification-inconsistent",
                first,
                rid.split("/")[-1],
                "labelled "
                + "; ".join(f"“{lbl}” on {', '.join(sorted(set(v)))}" for lbl, v in labels.items()),
                rid=rid,
            )

    # 3.2.6 Consistent Help: help entry's position among the screen's controls should match.
    places: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for s in screens:
        els = [e for e in s.get("elements", []) if e["action"] == "click" and e["kind"] != "back"]
        els.sort(key=lambda e: (e["bounds"][1] // 40, e["bounds"][0]))
        for idx, e in enumerate(els):
            if _HELP_RE.search(e.get("label", "")):
                rel = "top" if idx < len(els) / 3 else "bottom" if idx >= 2 * len(els) / 3 else "middle"
                places[normalize_text(e["label"])].append((s["id"], rel))
    for label, seen in places.items():
        if len({r for _, r in seen}) > 1:
            out.add("help-inconsistent", seen[0][0], label, ", ".join(f"{sid}: {r}" for sid, r in seen))


# ── along flows ──────────────────────────────────────────────────────────────


def _flow_checks(out: _Collector, data: dict, screens: list[dict]) -> None:
    by_id = {s["id"]: s for s in screens}
    # 3.3.7 Redundant Entry: the same field typed on two screens of one path from launch.
    for s in screens:
        path = [st["screen"] for st in s.get("reach_path", [])] + [s["id"]]
        seen: dict[str, str] = {}
        for sid in path:
            for f in by_id.get(sid, {}).get("autofill", []):
                k = normalize_text(f.get("label") or "")
                if not k or k in ("edittext", "text field"):
                    continue
                if k in seen and seen[k] != sid:
                    out.add(
                        "redundant-entry",
                        sid,
                        f.get("label", ""),
                        f"also typed on {seen[k]} earlier in the path to {s['id']}",
                        bounds=None,
                    )
                seen.setdefault(k, sid)
    # 3.2.2 On Input: typing changed the screen (recorded by the explorer).
    for ev in data.get("events", []):
        if ev.get("type") == "change_on_input":
            out.add("change-on-input", ev.get("screen") or "?", "typing", ev.get("detail", ""))


# ── app level ────────────────────────────────────────────────────────────────


def _app_checks(out: _Collector, data: dict) -> None:
    locked = data["run"].get("app", {}).get("orientation_locked") or {}
    for act, mode in locked.items():
        out.add("orientation-locked", "app", act.rsplit(".", 1)[-1], f"{act} is locked to {mode}")


def format_audit(rep: dict, level: str = "AAA") -> str:
    order = {"A": 0, "AA": 1, "AAA": 2}
    issues = [
        i for i in rep["issues"] if order[i["level"]] <= order[level] and i["triage"] in ("open", "confirmed")
    ]
    dens = "exact" if rep["density_exact"] else "estimated"
    lines = [
        f"WCAG 2.2 checks for {rep['run']} (level ≤ {level}; {dens} dp; font scale {rep.get('font_scale') or '?'})",
        f"  {len(issues)} open issue(s); automated findings need confirming, 'review' items a manual check",
    ]
    by_sc: dict[str, list[dict]] = defaultdict(list)
    for i in issues:
        by_sc[i["sc"]].append(i)
    for sc in sorted(by_sc, key=lambda x: [int(p) for p in x.split(".")]):
        r = RULES[by_sc[sc][0]["rule"]]
        lines.append(f"  {sc} {r.name} ({r.level}, {r.kind}) — {len(by_sc[sc])}")
        for i in by_sc[sc][:6]:
            lines.append(f"     {i['screen']:>6}  {i['label'][:34]!r:38} {i['detail'][:70]}")
        if len(by_sc[sc]) > 6:
            lines.append(f"     … {len(by_sc[sc]) - 6} more")
    return "\n".join(lines)
