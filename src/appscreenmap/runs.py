"""Run directory layout and the runs/index.json catalogue the web viewer reads.

Runs are grouped per project (one folder per app):

    runs/index.json
    runs/<project>/<run-id>/map.json      e.g. runs/sample-app/sample-app-20261013-015149/

Run ids stay flat and unique, so URLs keep the form /runs/<run-id>/… and the server resolves
them to the project folder. Older flat runs (runs/<run-id>/map.json) are still found.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .model import write_json_atomic

RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", s).strip("-").lower() or "app"


def project_for(package: str, project: str | None = None) -> str:
    """Default project folder: the last part of the package name (dev.mks.sample-app → sample-app)."""
    return slug(project or package.rsplit(".", 1)[-1])


def new_run_dir(runs_root: Path, package: str, name: str | None = None, project: str | None = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    proj = project_for(package, project)
    d = runs_root / proj / f"{slug(name) if name else proj}-{stamp}"
    d.mkdir(parents=True, exist_ok=False)
    return d


def iter_run_dirs(runs_root: Path):
    """Every run directory: runs/<project>/<run-id>/ and legacy runs/<run-id>/."""
    if not runs_root.is_dir():
        return
    for d in runs_root.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        if (d / "map.json").is_file():
            yield d
            continue
        for sub in d.iterdir():
            if sub.is_dir() and (sub / "map.json").is_file():
                yield sub


def resolve_run(runs_root: Path, run_id: str) -> Path | None:
    """The directory of run `run_id` (a bare id, not a path), wherever its project folder is."""
    if not RUN_ID_RE.fullmatch(run_id) or ".." in run_id:
        return None
    flat = runs_root / run_id
    if (flat / "map.json").is_file():
        return flat
    for d in runs_root.glob(f"*/{run_id}"):
        if (d / "map.json").is_file():
            return d
    return None


def update_index(runs_root: Path) -> list[dict]:
    rows = []
    for d in iter_run_dirs(runs_root):
        try:
            data = json.loads((d / "map.json").read_text())
        except (json.JSONDecodeError, OSError):
            continue
        run, stats = data.get("run", {}), data.get("stats", {})
        rel = d.relative_to(runs_root).as_posix()
        project = (
            d.parent.name
            if d.parent != runs_root
            else project_for(run.get("app", {}).get("package") or d.name)
        )
        first = next((s for s in data.get("screens", []) if s.get("kind") == "app"), None)
        diffs, verifies = [], []
        if (d / "diff").is_dir():
            diffs = sorted(p.name for p in (d / "diff").iterdir() if (p / "diff.json").is_file())
        if (d / "verify").is_dir():
            verifies = sorted(p.name for p in (d / "verify").iterdir() if (p / "verify.json").is_file())
        rows.append(
            {
                "id": d.name,
                "project": project,
                "path": rel,
                "status": run.get("status"),
                "started_at": run.get("started_at"),
                "finished_at": run.get("finished_at"),
                "app": run.get("app", {}),
                "device": run.get("device", {}),
                "steps": run.get("steps"),
                "elapsed_s": run.get("elapsed_s"),
                "screens": stats.get("screens", 0),
                "transitions": stats.get("transitions", 0),
                "crashes": stats.get("crashes", 0),
                "thumb": f"{rel}/{first['thumb']}" if first and first.get("thumb") else None,
                "diffs": diffs,
                "verifies": verifies,
            }
        )
    rows.sort(key=lambda r: (r["started_at"] or "", r["id"]), reverse=True)
    write_json_atomic(runs_root / "index.json", {"runs": rows})
    return rows
