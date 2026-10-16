"""Viewer notes: stars and notes people add to screens, plus accessibility-review decisions, from the web viewer.

Stored as `runs/<run-id>/notes.json` next to map.json, so they travel with the run, survive browser resets,
and can be committed. Written only through `appscreenmap serve` (PUT) or the viewer's dev server.
"""

from __future__ import annotations

import json
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
        "edits": _edits(data.get("edits", {})),
    }


def _num(v: object, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise NotesError(f"{what} must be a number")
    return float(v)


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
            "edits": {"titles": {}, "deleted": [], "parents": {}, "added": {}, "labels": {}},
        }
    return validate(json.loads(p.read_text()))
