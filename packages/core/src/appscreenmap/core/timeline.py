"""Tie timed rows (requests, log lines) to the screen that was showing when each one started."""

from __future__ import annotations

import bisect
import json
import os
from pathlib import Path

TIMELINE = "timeline.jsonl"


def attribute(rows: list[dict], timeline: list[dict]) -> list[dict]:
    """Copies of `rows` with `screen` (and `screen_title`, `step`) from the last `timeline` entry at or before each `t`.

    `timeline` is a list of `{"t", "screen", "title", "step"?}` in time order; `screen` is None while the app wasn't in
    front. Rows from before the first entry, or without a time, get no screen.
    """
    times = [e["t"] for e in timeline]
    out = []
    for r in rows:
        r = dict(r)
        i = bisect.bisect_right(times, r["t"]) - 1 if r.get("t") is not None else -1
        if i >= 0:
            r["screen"] = timeline[i].get("screen")
            if timeline[i].get("title"):
                r["screen_title"] = timeline[i]["title"]
            if timeline[i].get("step") is not None:
                r["step"] = timeline[i]["step"]
        out.append(r)
    return out


def read_rows(path: Path) -> list[dict]:
    """The JSON objects of a .jsonl file; other lines (and a missing file) are skipped."""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if isinstance(o, dict):
            rows.append(o)
    return rows


def write_rows(path: Path, rows: list[dict]) -> None:
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    os.replace(tmp, path)


def finish(run_dir: Path, titles: dict[str, str], captures: list[str]) -> dict[str, int]:
    """End of a crawl: give the timeline each screen's final title, then tie each capture file's rows to screens.

    A screen can be renamed after it was first seen (tabs, untitled menus), so titles come from the finished map.
    Returns the row count per capture file.
    """
    timeline = [
        {**e, "title": titles[e["screen"]]} if e.get("screen") in titles else e
        for e in read_rows(run_dir / TIMELINE)
    ]
    if (run_dir / TIMELINE).is_file():
        write_rows(run_dir / TIMELINE, timeline)
    return {name: len(attribute_file(run_dir / name, timeline)) for name in captures}


def attribute_file(path: Path, timeline: list[dict]) -> list[dict]:
    """Rewrite a capture file (network.jsonl, logs.jsonl) in place with each row's screen; returns the rows."""
    rows = attribute(read_rows(path), timeline)
    if Path(path).is_file():
        write_rows(path, rows)
    return rows
