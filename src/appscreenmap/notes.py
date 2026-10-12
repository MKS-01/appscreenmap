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
    return {"appscreenmap_notes": 1, "run": str(data.get("run") or ""), "notes": clean, "a11y": triage}


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
        return {"appscreenmap_notes": 1, "run": run_dir.name, "notes": {}, "a11y": {}}
    return validate(json.loads(p.read_text()))
