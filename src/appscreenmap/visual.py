"""Visual diff between two runs: match screens across builds, then compare them two ways.

- Pixels: changed ratio, the changed regions and whether each got brighter or darker.
- Text, from the view hierarchy: every string with its exact bounds, so text added, removed, moved
  or changed is reported precisely without OCR.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat

from .analyzer import jaccard, normalize_text, parse_hierarchy
from .model import load_map, write_json_atomic

PIXEL_TOLERANCE = 24  # per-channel difference ignored as rendering noise
MOVE_TOLERANCE = 0.01  # text that shifted less than this fraction of the screen hasn't moved
REGION_CELL = 16  # px; changed pixels are grouped into regions on a grid of this size
MAX_REGIONS = 12
_SPACE_RE = re.compile(r"\s+")

MARK_COLORS = {
    "added": (30, 160, 80),
    "changed": (235, 150, 0),
    "moved": (235, 150, 0),
    "removed": (40, 110, 230),
}


def _match(base: list[dict], cand: list[dict], threshold: float) -> list[tuple[dict, dict, float]]:
    """Greedy one-to-one matching: exact signature first, then best token similarity."""
    pairs: list[tuple[dict, dict, float]] = []
    used_b, used_c = set(), set()
    by_sig = {s["signature"]: s for s in base}
    for c in cand:
        if (b := by_sig.get(c["signature"])) and b["id"] not in used_b:
            pairs.append((b, c, 1.0))
            used_b.add(b["id"])
            used_c.add(c["id"])
    scored = []
    for b in base:
        if b["id"] in used_b:
            continue
        for c in cand:
            if c["id"] in used_c:
                continue
            sim = jaccard(frozenset(b.get("tokens", [])), frozenset(c.get("tokens", [])))
            if (b.get("activity") or "").rsplit(".", 1)[-1] == (c.get("activity") or "").rsplit(".", 1)[-1]:
                sim += 0.05
            if sim >= threshold:
                scored.append((sim, b, c))
    for sim, b, c in sorted(scored, key=lambda x: -x[0]):
        if b["id"] not in used_b and c["id"] not in used_c:
            pairs.append((b, c, round(min(sim, 1.0), 3)))
            used_b.add(b["id"])
            used_c.add(c["id"])
    return pairs


# ── text ─────────────────────────────────────────────────────────────────────


def text_nodes(xml: str, height: int, package: str | None = None, mask_top: float = 0.0) -> list[dict]:
    """Every visible string on a screen with its bounds. Other windows (status bar, keyboard) and the
    masked top band are left out."""
    out = []
    for n in parse_hierarchy(xml).walk():
        text = _SPACE_RE.sub(" ", (n.text or n.desc).strip())
        if not text or n.area == 0 or (package and n.package and n.package != package):
            continue
        if n.bounds[3] <= height * mask_top:
            continue
        out.append({"text": text, "rid": n.rid, "cls": n.short_cls, "bounds": list(n.bounds)})
    return out


def _norm(b: list[int], size: tuple[int, int]) -> tuple[float, float, float, float]:
    w, h = max(1, size[0]), max(1, size[1])
    return b[0] / w, b[1] / h, b[2] / w, b[3] / h


def _center_offset(a, b) -> tuple[float, float]:
    return abs((a[0] + a[2]) - (b[0] + b[2])) / 2, abs((a[1] + a[3]) - (b[1] + b[3])) / 2


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def text_diff(
    base: list[dict],
    cand: list[dict],
    base_size: tuple[int, int],
    cand_size: tuple[int, int],
    move_tolerance: float = MOVE_TOLERANCE,
) -> dict:
    """Compare two screens' strings. Positions are compared as fractions of the screen, so runs on
    different screen sizes still line up.

    Pairing, in order: the same string (nearest first) → unchanged or moved; the same resource id →
    changed; the same place and class → changed. What is left was removed or added.
    """
    nb = [_norm(n["bounds"], base_size) for n in base]
    nc = [_norm(n["bounds"], cand_size) for n in cand]
    left_b, left_c = set(range(len(base))), set(range(len(cand)))
    changes: list[dict] = []

    def pair(i: int, j: int, kind: str | None) -> None:
        left_b.discard(i)
        left_c.discard(j)
        if kind is None:
            return
        change = {
            "type": kind,
            "text": cand[j]["text"],
            "base_bounds": base[i]["bounds"],
            "cand_bounds": cand[j]["bounds"],
            "rid": cand[j]["rid"] or base[i]["rid"],
        }
        if kind == "changed":
            change["base_text"] = base[i]["text"]
            # Only digits differ (a clock, a counter): usually data, not a UI change.
            change["digits_only"] = normalize_text(base[i]["text"], 200) == normalize_text(
                cand[j]["text"], 200
            )
        changes.append(change)

    # 1. Same string: nearest pairs first.
    same = sorted(
        (sum(_center_offset(nb[i], nc[j])), i, j)
        for i in range(len(base))
        for j in range(len(cand))
        if base[i]["text"] == cand[j]["text"]
    )
    for _, i, j in same:
        if i in left_b and j in left_c:
            dx, dy = _center_offset(nb[i], nc[j])
            pair(i, j, "moved" if dx > move_tolerance or dy > move_tolerance else None)

    # 2. Same resource id (unique on both sides): the text of that view changed.
    def unique_rids(nodes, left):
        seen: dict[str, list[int]] = {}
        for k in left:
            if nodes[k]["rid"]:
                seen.setdefault(nodes[k]["rid"], []).append(k)
        return {r: ks[0] for r, ks in seen.items() if len(ks) == 1}

    rb, rc = unique_rids(base, left_b), unique_rids(cand, left_c)
    for rid in sorted(rb.keys() & rc.keys()):
        pair(rb[rid], rc[rid], "changed")

    # 3. Same place, same kind of view.
    overlap = sorted(
        (-_iou(nb[i], nc[j]), i, j)
        for i in left_b
        for j in left_c
        if base[i]["cls"] == cand[j]["cls"] and _iou(nb[i], nc[j]) >= 0.5
    )
    for _, i, j in overlap:
        if i in left_b and j in left_c:
            pair(i, j, "changed")

    for i in sorted(left_b):
        changes.append(
            {
                "type": "removed",
                "text": base[i]["text"],
                "base_bounds": base[i]["bounds"],
                "cand_bounds": None,
                "rid": base[i]["rid"],
            }
        )
    for j in sorted(left_c):
        changes.append(
            {
                "type": "added",
                "text": cand[j]["text"],
                "base_bounds": None,
                "cand_bounds": cand[j]["bounds"],
                "rid": cand[j]["rid"],
            }
        )
    changes.sort(
        key=lambda c: ((c["cand_bounds"] or c["base_bounds"])[1], (c["cand_bounds"] or c["base_bounds"])[0])
    )
    counts = {k: sum(1 for c in changes if c["type"] == k) for k in ("added", "removed", "moved", "changed")}
    return {**counts, "changes": changes}


def screen_text_diff(base_dir: Path, b: dict, cand_dir: Path, c: dict, mask_top: float) -> dict | None:
    """text_diff for two screens of two runs, or None when a hierarchy is missing."""
    if not (b.get("hierarchy") and c.get("hierarchy")):
        return None
    bx, cx = base_dir / b["hierarchy"], cand_dir / c["hierarchy"]
    if not (bx.is_file() and cx.is_file()):
        return None
    bs, cs = (
        (b.get("width") or 1080, b.get("height") or 2400),
        (c.get("width") or 1080, c.get("height") or 2400),
    )
    return text_diff(
        text_nodes(bx.read_text(), bs[1], b.get("package"), mask_top),
        text_nodes(cx.read_text(), cs[1], c.get("package"), mask_top),
        bs,
        cs,
    )


def text_changed(diff: dict | None) -> bool:
    """Whether a text diff shows a real UI change (digit-only changes are data, like a clock)."""
    return bool(diff) and any(not c.get("digits_only") for c in diff["changes"])


# ── pixels ───────────────────────────────────────────────────────────────────


def changed_regions(mask: Image.Image, a: Image.Image, b: Image.Image, cell: int = REGION_CELL) -> list[dict]:
    """Group changed pixels into regions (connected cells of a grid) and say whether each region got
    brighter or darker in the candidate."""
    w, h = mask.size
    gw, gh = max(1, w // cell), max(1, h // cell)
    grid = mask.resize((gw, gh), Image.Resampling.BOX).load()
    seen: set[tuple[int, int]] = set()
    regions = []
    for y0 in range(gh):
        for x0 in range(gw):
            if (x0, y0) in seen or grid[x0, y0] < 8:  # < ~3% of a cell changed: noise
                continue
            seen.add((x0, y0))
            queue, x1, y1, x2, y2, cells = deque([(x0, y0)]), x0, y0, x0, y0, 0
            while queue:
                x, y = queue.popleft()
                cells += 1
                x1, y1, x2, y2 = min(x1, x), min(y1, y), max(x2, x), max(y2, y)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        n = (x + dx, y + dy)
                        if 0 <= n[0] < gw and 0 <= n[1] < gh and n not in seen and grid[n] >= 8:
                            seen.add(n)
                            queue.append(n)
            box = (x1 * cell, y1 * cell, min(w, (x2 + 1) * cell), min(h, (y2 + 1) * cell))
            delta = (
                ImageStat.Stat(b.convert("L").crop(box)).mean[0]
                - ImageStat.Stat(a.convert("L").crop(box)).mean[0]
            )
            direction = "brighter" if delta > 4 else "darker" if delta < -4 else "changed"
            regions.append(
                {"bounds": list(box), "cells": cells, "direction": direction, "delta": round(delta, 1)}
            )
    regions.sort(key=lambda r: -r["cells"])
    return regions[:MAX_REGIONS]


def compare_images(
    a: Path, b: Path, out: Path, mask_top: float, mask_bottom: float, marks: list[dict] | None = None
) -> dict:
    """Pixel diff of two screenshots, written as an overlay PNG. `marks` (text changes from
    text_diff) are outlined on the overlay: added green, changed/moved amber, removed blue."""
    with Image.open(a) as ia, Image.open(b) as ib:
        ia, ib = ia.convert("RGB"), ib.convert("RGB")
        scale = (ia.size[0] / ib.size[0], ia.size[1] / ib.size[1])
        if ia.size != ib.size:
            ib = ib.resize(ia.size)
        w, h = ia.size
        top, bottom = int(h * mask_top), h - int(h * mask_bottom)
        diff = ImageChops.difference(ia, ib).convert("L").point(lambda v: 255 if v > PIXEL_TOLERANCE else 0)
        ImageDraw.Draw(diff).rectangle([0, 0, w, top], fill=0)
        if bottom < h:
            ImageDraw.Draw(diff).rectangle([0, bottom, w, h], fill=0)
        changed = sum(diff.histogram()[255:])
        ratio = changed / max(1, w * (bottom - top))
        bbox = diff.getbbox()
        regions = changed_regions(diff, ia, ib) if bbox else []
        # Overlay: candidate dimmed, changed pixels in red, change bbox outlined, text changes boxed.
        overlay = Image.blend(ib, Image.new("RGB", ib.size, (255, 255, 255)), 0.55)
        overlay.paste(Image.new("RGB", ib.size, (230, 30, 60)), mask=diff)
        draw = ImageDraw.Draw(overlay)
        if bbox:
            draw.rectangle(bbox, outline=(230, 30, 60), width=4)
        for m in marks or []:
            if m["type"] == "removed":
                box = m["base_bounds"]
            else:
                cb = m["cand_bounds"]
                box = [cb[0] * scale[0], cb[1] * scale[1], cb[2] * scale[0], cb[3] * scale[1]]
            draw.rectangle(box, outline=MARK_COLORS[m["type"]], width=5)
        overlay.thumbnail((540, 1200))
        overlay.save(out, "PNG", optimize=True)
    return {"changed_ratio": round(ratio, 5), "bbox": list(bbox) if bbox else None, "regions": regions}


def diff_runs(
    base_dir: str | Path,
    cand_dir: str | Path,
    threshold: float = 0.6,
    mask_top: float = 0.045,
    mask_bottom: float = 0.0,
    changed_above: float = 0.002,
) -> dict:
    base_dir, cand_dir = Path(base_dir), Path(cand_dir)
    base, cand = load_map(base_dir), load_map(cand_dir)
    b_screens = [s for s in base["screens"] if s["kind"] == "app" and s.get("screenshot")]
    c_screens = [s for s in cand["screens"] if s["kind"] == "app" and s.get("screenshot")]
    out_dir = cand_dir / "diff" / base["run"]["id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    items = []
    pairs = _match(b_screens, c_screens, threshold)
    for b, c, sim in pairs:
        img = out_dir / f"{b['id']}__{c['id']}.png"
        text = screen_text_diff(base_dir, b, cand_dir, c, mask_top)
        res = compare_images(
            base_dir / b["screenshot"],
            cand_dir / c["screenshot"],
            img,
            mask_top,
            mask_bottom,
            marks=[m for m in text["changes"] if not m.get("digits_only")] if text else None,
        )
        changed = res["changed_ratio"] > changed_above or text_changed(text)
        items.append(
            {
                "status": "changed" if changed else "same",
                "text": text,
                "base": b["id"],
                "cand": c["id"],
                "title": c.get("title"),
                "similarity": sim,
                "diff": f"diff/{base['run']['id']}/{img.name}",
                **res,
            }
        )
    matched_b = {p[0]["id"] for p in pairs}
    matched_c = {p[1]["id"] for p in pairs}
    items += [
        {"status": "missing", "base": s["id"], "cand": None, "title": s.get("title")}
        for s in b_screens
        if s["id"] not in matched_b
    ]
    items += [
        {"status": "new", "base": None, "cand": s["id"], "title": s.get("title")}
        for s in c_screens
        if s["id"] not in matched_c
    ]
    order = {"changed": 0, "new": 1, "missing": 2, "same": 3}
    items.sort(key=lambda i: (order[i["status"]], -(i.get("changed_ratio") or 0)))
    summary = {s: sum(1 for i in items if i["status"] == s) for s in order}
    report = {
        "base_run": base["run"]["id"],
        "cand_run": cand["run"]["id"],
        "base_app": base["run"]["app"],
        "cand_app": cand["run"]["app"],
        "summary": summary,
        "items": items,
    }
    write_json_atomic(out_dir / "diff.json", report)
    return report
