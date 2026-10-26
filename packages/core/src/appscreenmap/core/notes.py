"""Viewer notes: stars and notes people add to screens, plus accessibility-review decisions, from the web viewer.

Stored as `runs/<run-id>/notes.json` next to map.json, so they travel with the run, survive browser resets,
and can be committed. Written only through `appscreenmap serve` (PUT) or the viewer's dev server.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .model import write_json_atomic
from .runs import resolve_run

NOTES_FILE = "notes.json"
MAX_BYTES = 1_000_000
TRIAGE_STATUSES = ("confirmed", "wontfix", "false_positive")
COMMENT_TAGS = ("bug", "flow", "copy", "question")
COMMENT_STATUSES = ("open", "resolved")
MAX_REPLIES = 100
MAX_STICKY_TEXT = 4000
MAX_STICKIES = 1000
MAX_LAYOUT = 5000  # card positions
MAX_TREE_ORDER = 1000
MAX_COORD = 1e6
_RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


class NotesError(ValueError):
    pass


def run_dir_for(runs_root: Path, run_id: str) -> Path | None:
    """The run directory for `run_id` (runs/<project>/<run-id>/ or legacy runs/<run-id>/), or None."""
    if not _RUN_RE.fullmatch(run_id) or ".." in run_id:
        return None
    return resolve_run(runs_root, run_id)


def validate(data: object) -> dict:
    if (
        not isinstance(data, dict)
        or data.get("appscreenmap_notes") != 1
        or not isinstance(data.get("notes"), dict)
    ):
        raise NotesError("not an AppScreenMap notes document")
    clean: dict[str, dict] = {}
    for sid, n in data["notes"].items():
        if not isinstance(sid, str) or not isinstance(n, dict):
            raise NotesError(f"bad note for {sid!r}")
        entry = {"updated": str(n.get("updated") or "")}
        if n.get("star"):
            entry["star"] = True
        if isinstance(n.get("note"), str) and n["note"].strip():
            entry["note"] = n["note"]
        if len(entry) > 1:
            clean[sid] = entry
    # Accessibility review decisions, keyed by the viewer's issue key.
    a11y = data.get("a11y", {})
    if not isinstance(a11y, dict):
        raise NotesError("a11y must be an object")
    triage: dict[str, dict] = {}
    for key, t in a11y.items():
        if not isinstance(key, str) or not isinstance(t, dict) or t.get("status") not in TRIAGE_STATUSES:
            raise NotesError(f"bad a11y decision for {key!r}")
        entry = {"status": t["status"], "updated": str(t.get("updated") or "")}
        if isinstance(t.get("note"), str) and t["note"].strip():
            entry["note"] = t["note"]
        triage[key] = entry
    return {
        "appscreenmap_notes": 1,
        "run": str(data.get("run") or ""),
        "notes": clean,
        "a11y": triage,
        "comments": _comments(data.get("comments", {})),
        "stickies": _stickies(data.get("stickies", {})),
        "edits": _edits(data.get("edits", {})),
        "layout": _layout(data.get("layout", {})),
        "tree_order": _tree_order(data.get("tree_order", [])),
    }


def _num(v: object, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise NotesError(f"{what} must be a number")
    v = float(v)
    if not math.isfinite(v) or abs(v) > MAX_COORD:
        raise NotesError(f"{what} is out of range")
    return v


def _layout(raw: object) -> dict[str, dict]:
    """Where a card was dragged to on the canvas, by screen id (flow coordinates). Kept here, not in the browser, so a
    cleared cache doesn't lose it and everyone who opens the canvas sees the same arrangement."""
    if not isinstance(raw, dict):
        raise NotesError("layout must be an object")
    if len(raw) > MAX_LAYOUT:
        raise NotesError("layout has too many cards")
    out: dict[str, dict] = {}
    for sid, p in raw.items():
        if not isinstance(sid, str) or not sid or len(sid) > 64 or not isinstance(p, dict):
            raise NotesError(f"bad layout entry {sid!r}")
        x, y = _num(p.get("x"), f"{sid} x"), _num(p.get("y"), f"{sid} y")
        if not (math.isfinite(x) and math.isfinite(y)) or abs(x) > MAX_COORD or abs(y) > MAX_COORD:
            raise NotesError(f"layout position of {sid!r} is out of range")
        out[sid] = {"x": x, "y": y}
    return out


def _tree_order(raw: object) -> list[str]:
    """The roots of the canvas's trees, left to right; a root not listed keeps its place after the listed ones."""
    if not isinstance(raw, list) or len(raw) > MAX_TREE_ORDER:
        raise NotesError("tree_order must be a list of screen ids")
    if not all(isinstance(i, str) and i and len(i) <= 64 for i in raw):
        raise NotesError("tree_order holds screen ids")
    return list(dict.fromkeys(raw))


def _comments(raw: object) -> dict[str, dict]:
    """Figma-style pins on the map: a point on the canvas, or an offset on a screen so it follows the screen."""
    if not isinstance(raw, dict):
        raise NotesError("comments must be an object")
    out: dict[str, dict] = {}
    for cid, c in raw.items():
        if not isinstance(cid, str) or not isinstance(c, dict):
            raise NotesError(f"bad comment {cid!r}")
        text = c.get("text")
        if not isinstance(text, str) or not text.strip():
            raise NotesError(f"comment {cid!r} has no text")
        entry: dict = {
            "id": cid,
            "x": _num(c.get("x", 0), "x"),
            "y": _num(c.get("y", 0), "y"),
            "tag": c.get("tag") if c.get("tag") in COMMENT_TAGS else "flow",
            "status": c.get("status") if c.get("status") in COMMENT_STATUSES else "open",
            "text": text,
            "created": str(c.get("created") or ""),
            "updated": str(c.get("updated") or ""),
            "replies": [],
        }
        if isinstance(c.get("screen"), str) and c["screen"]:
            entry["screen"] = c["screen"]  # x, y are then an offset from the screen card's top-left
        if isinstance(c.get("author"), str) and c["author"]:
            entry["author"] = c["author"]
        for r in (c.get("replies") or [])[:MAX_REPLIES]:
            if isinstance(r, dict) and isinstance(r.get("text"), str) and r["text"].strip():
                entry["replies"].append({"text": r["text"], "created": str(r.get("created") or "")})
        out[cid] = entry
    return out


def _stickies(raw: object) -> dict[str, dict]:
    """Sticky notes on the canvas: free text placed around a feature, on a point or (with "screen") on a screen."""
    if not isinstance(raw, dict):
        raise NotesError("stickies must be an object")
    if len(raw) > MAX_STICKIES:
        raise NotesError("too many stickies")
    out: dict[str, dict] = {}
    for sid, n in raw.items():
        if not isinstance(sid, str) or not isinstance(n, dict):
            raise NotesError(f"bad sticky {sid!r}")
        text = n.get("text")
        if not isinstance(text, str):
            raise NotesError(f"sticky {sid!r} has no text")
        entry: dict = {
            "id": sid,
            "x": _num(n.get("x", 0), "x"),
            "y": _num(n.get("y", 0), "y"),
            "text": text[:MAX_STICKY_TEXT],
            "created": str(n.get("created") or ""),
            "updated": str(n.get("updated") or ""),
        }
        if isinstance(n.get("screen"), str) and n["screen"]:
            entry["screen"] = n["screen"]  # x, y are then an offset from the screen card's top-left
        out[sid] = entry
    return out


def _edits(raw: object) -> dict:
    """Changes to the tree made in the viewer, kept apart from map.json: renamed screens, screens taken out of the
    tree, screens moved under another one (parent null: a root of its own), planned screens the crawl has not found,
    and relabelled links (keyed by the screen the link leads into)."""
    if not isinstance(raw, dict):
        raise NotesError("edits must be an object")
    titles = raw.get("titles", {})
    deleted = raw.get("deleted", [])
    parents = raw.get("parents", {})
    added = raw.get("added", {})
    labels = raw.get("labels", {})
    if not all(isinstance(x, dict) for x in (titles, parents, added, labels)) or not isinstance(
        deleted, list
    ):
        raise NotesError("bad edits")
    planned: dict[str, dict] = {}
    for k, v in added.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            raise NotesError(f"bad planned screen {k!r}")
        title, parent = v.get("title"), v.get("parent")
        if not isinstance(title, str) or not title.strip():
            raise NotesError(f"planned screen {k!r} has no title")
        if parent is not None and not isinstance(parent, str):
            raise NotesError(f"planned screen {k!r} has a bad parent")
        planned[k] = {"title": title, "parent": parent, "created": str(v.get("created") or "")}
    return {
        "added": planned,
        "labels": {
            k: v for k, v in labels.items() if isinstance(k, str) and isinstance(v, str) and v.strip()
        },
        "titles": {
            k: v for k, v in titles.items() if isinstance(k, str) and isinstance(v, str) and v.strip()
        },
        "deleted": sorted({d for d in deleted if isinstance(d, str)}),
        "parents": {
            k: v for k, v in parents.items() if isinstance(k, str) and (v is None or isinstance(v, str))
        },
    }


def save(run_dir: Path, raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        raise NotesError("notes document too large")
    try:
        data = validate(json.loads(raw))
    except json.JSONDecodeError as e:
        raise NotesError(f"invalid JSON: {e}") from e
    data["run"] = run_dir.name
    write_json_atomic(run_dir / NOTES_FILE, data)
    return data


def load(run_dir: Path) -> dict:
    p = run_dir / NOTES_FILE
    if not p.is_file():
        return {
            "appscreenmap_notes": 1,
            "run": run_dir.name,
            "notes": {},
            "a11y": {},
            "comments": {},
            "stickies": {},
            "edits": {"titles": {}, "deleted": [], "parents": {}, "added": {}, "labels": {}},
            "layout": {},
            "tree_order": [],
        }
    return validate(json.loads(p.read_text()))
