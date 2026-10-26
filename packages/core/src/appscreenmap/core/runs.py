"""Run directory layout and the runs/index.json catalogue the web viewer reads.

Runs are grouped per project (one folder per app):

    runs/index.json
    runs/<project>/<run-id>/map.json      e.g. runs/playground/playground-v1-20261013-031007/

Run ids stay flat and unique, so URLs keep the form /runs/<run-id>/… and the server resolves
them to the project folder. Older flat runs (runs/<run-id>/map.json) are still found.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from .model import write_json_atomic

RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", s).strip("-").lower() or "app"


def project_for(package: str, project: str | None = None) -> str:
    """Default project folder: the last part of the package name (dev.appscreenmap.playground → playground)."""
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


class RunDeleteError(ValueError):
    pass


def delete_run(runs_root: Path, key: str) -> Path:
    """Delete one run folder: `key` is `<project>/<run-id>` (the index `path`) or a bare run id. Refuses anything that is
    not a run inside `runs_root`, and a crawl that is still running. Rebuilds index.json; returns the deleted folder."""
    root = runs_root.resolve()
    parts = key.strip("/").split("/")
    if not 1 <= len(parts) <= 2 or not all(RUN_ID_RE.fullmatch(p) and ".." not in p for p in parts):
        raise RunDeleteError(f"not a run: {key!r}")
    run_dir = (root / parts[0] / parts[1]).resolve() if len(parts) == 2 else resolve_run(root, parts[0])
    if run_dir is not None:
        run_dir = run_dir.resolve()
    if run_dir is None or root not in run_dir.parents or not (run_dir / "map.json").is_file():
        raise RunDeleteError(f"no run {key!r}")
    try:
        status = json.loads((run_dir / "map.json").read_text()).get("run", {}).get("status")
    except (OSError, ValueError):
        status = None
    if status == "running":
        raise RunDeleteError("the crawl is still running; stop it first")
    shutil.rmtree(run_dir)
    update_index(runs_root)
    return run_dir


def _stack_summary(run_dir: Path) -> dict | None:
    """The one line a project card shows from `audits/stack.json` (written by `appscreenmap stack`)."""
    try:
        audit = json.loads((run_dir / "audits" / "stack.json").read_text())
    except (OSError, ValueError):
        return None
    facts = audit.get("facts") or {}
    return {
        "kind": (facts.get("stack") or {}).get("kind"),
        "summary": audit.get("summary"),
        "version": facts.get("version"),
        "generated_at": audit.get("generated_at"),
    }


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
        stack = _stack_summary(d)
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
                **({"stack": stack} if stack else {}),
            }
        )
    rows.sort(key=lambda r: (r["started_at"] or "", r["id"]), reverse=True)
    write_json_atomic(runs_root / "index.json", {"runs": rows})
    return rows
