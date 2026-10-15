"""One SVG of the whole map: every screen with its screenshot, every transition as an arrow.

The file is self-contained (screenshots are embedded as data URIs), so it opens in any browser and imports into Figma,
FigJam and other design tools. It uses plain presentation attributes and drawn arrowheads, no CSS or markers, because
design tools import those unevenly. Screens keep their id as the layer name (`s001-Sign-in`).
"""

from __future__ import annotations

import base64
import math
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

LAYOUTS = ("tree", "graph", "storyboard")
THEMES = {
    "light": {
        "bg": "#ffffff",
        "card": "#f6f7f9",
        "line": "#c9ced6",
        "text": "#1a1d23",
        "dim": "#646b78",
        "accent": "#0a62c9",
        "edge": "#8a92a0",
        "halo": "#ffffff",
    },
    "dark": {
        "bg": "#0a0a0a",
        "card": "#121212",
        "line": "#333333",
        "text": "#f0f0f0",
        "dim": "#a3a3a3",
        "accent": "#4da3ff",
        "edge": "#8a8a8a",
        "halo": "#0a0a0a",
    },
}
FONT = "Geist, Inter, Helvetica, Arial, sans-serif"
MONO = "Geist Mono, Menlo, Consolas, monospace"
IMG_W = 240  # width of a screenshot in the drawing, px
PAD = 12
TITLE_H = 44
H_GAP, V_GAP = 150, 70
MARGIN = 80
HEADER_H = 70
MAX_IMG_H = 620


@dataclass
class Node:
    id: str
    title: str
    kind: str
    img_path: Path | None
    img_h: int
    depth: int = 0
    step: int = 0
    x: float = 0
    y: float = 0
    children: list[str] = field(default_factory=list)

    @property
    def w(self) -> int:
        return IMG_W + 2 * PAD

    @property
    def h(self) -> int:
        return self.img_h + TITLE_H + 2 * PAD


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:40]


def _nodes(data: dict, run_dir: Path, full_res: bool) -> dict[str, Node]:
    out: dict[str, Node] = {}
    for s in data["screens"]:
        w, h = s.get("width") or 0, s.get("height") or 0
        img_h = min(MAX_IMG_H, round(IMG_W * h / w)) if w and h else round(IMG_W * 2.0)
        if s.get("kind") != "app":
            img_h = 120
        rel = (s.get("screenshot") if full_res else s.get("thumb")) or s.get("thumb") or s.get("screenshot")
        path = run_dir / rel if rel and s.get("kind") == "app" else None
        out[s["id"]] = Node(
            id=s["id"],
            title=(s.get("title") or s["id"]).strip() or s["id"],
            kind=s.get("kind") or "app",
            img_path=path if path and path.is_file() else None,
            img_h=img_h,
            depth=s["depth"] if isinstance(s.get("depth"), int) else -1,
            step=s.get("first_step") or 0,
        )
    return out


def _edges(data: dict, nodes: dict[str, Node]) -> list[dict]:
    """One edge per (from, to) pair; labels of repeated transitions are joined."""
    merged: dict[tuple[str, str], dict] = {}
    for t in data["transitions"]:
        a, b = t["from"], t["to"]
        if a == b or a not in nodes or b not in nodes:
            continue
        e = merged.setdefault(
            (a, b), {"from": a, "to": b, "labels": [], "step": t.get("step") or 0, "inferred": True}
        )
        label = (t.get("label") or t.get("action") or "").strip()
        if label and label not in e["labels"]:
            e["labels"].append(label)
        e["step"] = min(e["step"], t.get("step") or e["step"])
        e["inferred"] = e["inferred"] and bool(t.get("inferred"))
    return sorted(merged.values(), key=lambda e: e["step"])


def _structure(nodes: dict[str, Node], edges: list[dict]) -> tuple[list[str], dict[str, str]]:
    """Roots and a spanning tree: every screen hangs under the earliest screen that reached it."""
    order = sorted(nodes.values(), key=lambda n: (n.step or 10**9, n.id))
    incoming: dict[str, list[dict]] = {}
    for e in edges:
        incoming.setdefault(e["to"], []).append(e)
    roots = [n.id for n in order if n.depth == 0] or ([order[0].id] if order else [])
    parent: dict[str, str] = {}
    seen = set(roots)
    queue = list(roots)
    while queue:  # breadth first over real transitions, so depth is the shortest way in
        cur = queue.pop(0)
        for e in edges:
            if e["from"] == cur and e["to"] not in seen:
                seen.add(e["to"])
                parent[e["to"]] = cur
                nodes[e["to"]].depth = nodes[cur].depth + 1
                queue.append(e["to"])
    for n in order:  # unreachable screens become extra roots
        if n.id not in seen:
            seen.add(n.id)
            roots.append(n.id)
            n.depth = 0
    for r in roots:
        nodes[r].depth = 0
    for c, p in parent.items():
        nodes[p].children.append(c)
    for n in nodes.values():
        n.children.sort(key=lambda c: (nodes[c].step or 10**9, c))
    return roots, parent


def _layout_tree(nodes: dict[str, Node], roots: list[str]) -> None:
    slot = [0.0]
    row_h = max((n.h for n in nodes.values()), default=0) + V_GAP

    def place(nid: str) -> None:
        n = nodes[nid]
        if not n.children:
            n.x = slot[0] * (IMG_W + 2 * PAD + 60)
            slot[0] += 1
        else:
            for c in n.children:
                place(c)
            n.x = (nodes[n.children[0]].x + nodes[n.children[-1]].x) / 2
        n.y = n.depth * row_h

    for r in roots:
        place(r)


def _layout_graph(nodes: dict[str, Node]) -> None:
    """Columns by depth, left to right. A depth with too many screens wraps into side-by-side columns, so the
    drawing stays roughly landscape instead of one very tall strip."""
    by_depth: dict[int, list[Node]] = {}
    for n in sorted(nodes.values(), key=lambda n: (n.step or 10**9, n.id)):
        by_depth.setdefault(n.depth, []).append(n)
    area = sum((n.w + H_GAP) * (n.h + V_GAP) for n in nodes.values())
    limit = max(max(n.h for n in nodes.values()), math.sqrt(area / 1.6))
    columns: list[list[Node]] = []
    for d in sorted(by_depth):
        col: list[Node] = []
        used = 0.0
        for n in by_depth[d]:
            if col and used + V_GAP + n.h > limit:
                columns.append(col)
                col, used = [], 0.0
            used += (V_GAP if col else 0) + n.h
            col.append(n)
        columns.append(col)
    heights = [sum(n.h for n in c) + V_GAP * (len(c) - 1) for c in columns]
    tallest = max(heights, default=0)
    for i, (col, h) in enumerate(zip(columns, heights, strict=True)):
        y = (tallest - h) / 2
        for n in col:
            n.x = i * (IMG_W + 2 * PAD + H_GAP)
            n.y = y
            y += n.h + V_GAP


def _layout_storyboard(nodes: dict[str, Node]) -> None:
    ordered = sorted(nodes.values(), key=lambda n: (n.step or 10**9, n.id))
    per_row = max(1, min(5, math.ceil(math.sqrt(len(ordered) * 1.6))))
    row_h = max((n.h for n in ordered), default=0) + V_GAP
    for i, n in enumerate(ordered):
        n.x = (i % per_row) * (IMG_W + 2 * PAD + 60)
        n.y = (i // per_row) * row_h


def _arrow_head(x: float, y: float, dx: float, dy: float, color: str, size: float = 9) -> str:
    length = math.hypot(dx, dy) or 1
    ux, uy = dx / length, dy / length
    bx, by = x - ux * size, y - uy * size
    px, py = -uy * size / 2.2, ux * size / 2.2
    return f'<path d="M{x:.1f} {y:.1f} L{bx + px:.1f} {by + py:.1f} L{bx - px:.1f} {by - py:.1f} Z" fill="{color}"/>'


def _edge(e: dict, nodes: dict[str, Node], layout: str, th: dict, tree_edge: bool) -> str:
    a, b = nodes[e["from"]], nodes[e["to"]]
    if layout == "tree":
        x1, y1 = a.x + a.w / 2, a.y + a.h
        x2, y2 = b.x + b.w / 2, b.y
        if y2 <= y1:  # a link back up or sideways: leave from the side
            x1, y1, x2, y2 = a.x + a.w, a.y + a.h / 2, b.x + b.w, b.y + b.h / 2
            d = 90
            c1, c2 = (x1 + d, y1), (x2 + d, y2)
        else:
            my = (y1 + y2) / 2
            c1, c2 = (x1, my), (x2, my)
    else:
        if b.x > a.x:
            x1, y1, x2, y2 = a.x + a.w, a.y + a.h / 2, b.x, b.y + b.h / 2
            dx = (x2 - x1) / 2
            c1, c2 = (x1 + dx, y1), (x2 - dx, y2)
        else:  # back or same column: loop out on the right
            x1, y1, x2, y2 = a.x + a.w, a.y + a.h / 2, b.x + b.w, b.y + b.h / 2
            c1, c2 = (x1 + 110, y1), (x2 + 110, y2)
    dash = "" if tree_edge or layout == "graph" else ' stroke-dasharray="6 5"'
    color = th["edge"]
    out = (
        f'<path d="M{x1:.1f} {y1:.1f} C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {x2:.1f} {y2:.1f}" '
        f'fill="none" stroke="{color}" stroke-width="1.6"{dash}/>'
    )
    out += _arrow_head(x2, y2, x2 - c2[0] or 0.001, y2 - c2[1], color)
    label = " · ".join(e["labels"])
    if label:
        label = label if len(label) <= 28 else label[:27] + "…"
        mx = 0.125 * x1 + 0.375 * c1[0] + 0.375 * c2[0] + 0.125 * x2
        my = 0.125 * y1 + 0.375 * c1[1] + 0.375 * c2[1] + 0.125 * y2
        w = 6.4 * len(label) + 12
        out += (
            f'<rect x="{mx - w / 2:.1f}" y="{my - 10:.1f}" width="{w:.1f}" height="20" rx="5" fill="{th["halo"]}" '
            f'stroke="{th["line"]}" stroke-width="1"/>'
            f'<text x="{mx:.1f}" y="{my + 4:.1f}" text-anchor="middle" font-family={quoteattr(FONT)} font-size="11" '
            f'fill="{th["dim"]}">{escape(label)}</text>'
        )
    return out


def _image_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _node(n: Node, th: dict, badge: str) -> str:
    gid = f"{n.id}-{_slug(n.title)}".rstrip("-")
    out = [f"<g id={quoteattr(gid)}>"]
    out.append(
        f'<text x="{n.x:.1f}" y="{n.y - 8:.1f}" font-family={quoteattr(MONO)} font-size="11" fill="{th["accent"]}">'
        f"{escape(badge)}</text>"
    )
    dash = "" if n.kind == "app" else ' stroke-dasharray="6 5"'
    out.append(
        f'<rect x="{n.x:.1f}" y="{n.y:.1f}" width="{n.w}" height="{n.h}" rx="14" fill="{th["card"]}" '
        f'stroke="{th["line"]}" stroke-width="1.2"{dash}/>'
    )
    ix, iy = n.x + PAD, n.y + PAD
    if n.img_path:
        out.append(
            f'<clipPath id="clip-{n.id}"><rect x="{ix:.1f}" y="{iy:.1f}" width="{IMG_W}" height="{n.img_h}" rx="8"/></clipPath>'
            f'<image x="{ix:.1f}" y="{iy:.1f}" width="{IMG_W}" height="{n.img_h}" preserveAspectRatio="xMidYMin slice" '
            f'clip-path="url(#clip-{n.id})" xlink:href="{_image_uri(n.img_path)}"/>'
        )
    else:
        note = "left the app" if n.kind != "app" else "no screenshot"
        out.append(
            f'<rect x="{ix:.1f}" y="{iy:.1f}" width="{IMG_W}" height="{n.img_h}" rx="8" fill="none" stroke="{th["line"]}" '
            f'stroke-dasharray="4 4"/>'
            f'<text x="{ix + IMG_W / 2:.1f}" y="{iy + n.img_h / 2:.1f}" text-anchor="middle" font-family={quoteattr(FONT)} '
            f'font-size="12" fill="{th["dim"]}">{note}</text>'
        )
    lines = textwrap.wrap(n.title, 30)[:2] or [n.id]
    if len(textwrap.wrap(n.title, 30)) > 2:
        lines[1] = lines[1][:28] + "…"
    for i, line in enumerate(lines):
        out.append(
            f'<text x="{ix:.1f}" y="{iy + n.img_h + 20 + i * 16:.1f}" font-family={quoteattr(FONT)} font-size="13" '
            f'font-weight="600" fill="{th["text"]}">{escape(line)}</text>'
        )
    out.append("</g>")
    return "".join(out)


def map_svg(
    data: dict, run_dir: str | Path, layout: str = "tree", full_res: bool = True, theme: str = "light"
) -> str:
    """The map as one SVG document. `layout` is tree, graph or storyboard; `full_res` embeds the full screenshots."""
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be one of {', '.join(LAYOUTS)}")
    th = THEMES[theme]
    run_dir = Path(run_dir)
    nodes = _nodes(data, run_dir, full_res)
    if not nodes:
        raise ValueError("this run has no screens to draw")
    edges = _edges(data, nodes)
    roots, parent = _structure(nodes, edges)
    {
        "tree": lambda: _layout_tree(nodes, roots),
        "graph": lambda: _layout_graph(nodes),
        "storyboard": lambda: _layout_storyboard(nodes),
    }[layout]()
    min_x = min(n.x for n in nodes.values())
    min_y = min(n.y for n in nodes.values())
    for n in nodes.values():
        n.x += MARGIN - min_x
        n.y += MARGIN + HEADER_H - min_y
    extra = 110 if layout != "storyboard" else 0  # room for loops drawn on the right
    width = math.ceil(max(n.x + n.w for n in nodes.values()) + MARGIN + extra)
    height = math.ceil(max(n.y + n.h for n in nodes.values()) + MARGIN)
    app = (data.get("run") or {}).get("app") or {}
    run_id = (data.get("run") or {}).get("id", "")
    head = f"{app.get('label') or app.get('package') or 'App'} · {run_id}"
    sub = f"{len(nodes)} screens · {len(edges)} transitions · {layout}"
    out = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        ),
        f"<title>{escape(head)}</title>",
        f'<rect width="{width}" height="{height}" fill="{th["bg"]}"/>',
        f'<text x="{MARGIN}" y="{MARGIN - 8}" font-family={quoteattr(FONT)} font-size="26" font-weight="600" fill="{th["text"]}">{escape(head)}</text>',
        f'<text x="{MARGIN}" y="{MARGIN + 18}" font-family={quoteattr(MONO)} font-size="12" fill="{th["dim"]}">{escape(sub)}</text>',
    ]
    if layout != "storyboard":
        out.append('<g id="transitions">')
        for e in edges:
            is_tree = parent.get(e["to"]) == e["from"]
            if layout == "tree" and not is_tree:
                continue  # the tree shows how each screen was first reached; the graph layout shows every link
            out.append(_edge(e, nodes, layout, th, is_tree))
        out.append("</g>")
    out.append('<g id="screens">')
    ordered = sorted(nodes.values(), key=lambda n: (n.step or 10**9, n.id))
    for i, n in enumerate(ordered, 1):
        out.append(_node(n, th, f"{i:02d} · {n.id}" if layout == "storyboard" else n.id))
    out.append("</g></svg>\n")
    return "\n".join(out)


def write_map_svg(
    run_dir: str | Path,
    layout: str = "tree",
    full_res: bool = True,
    theme: str = "light",
    out: str | Path | None = None,
) -> Path:
    from appscreenmap.core.model import load_map

    run_dir = Path(run_dir)
    path = Path(out) if out else run_dir / f"map-{layout}.svg"
    path.write_text(map_svg(load_map(run_dir), run_dir, layout, full_res, theme))
    return path
