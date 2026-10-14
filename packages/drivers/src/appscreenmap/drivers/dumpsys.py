"""Parsers for `dumpsys gfxinfo` and `am start -W` output (pure functions, unit tested)."""

from __future__ import annotations

import re

TOTAL_FRAMES_RE = re.compile(r"Total frames rendered: (\d+)")


def parse_gfx_summary(text: str) -> dict:
    """Summary block of `dumpsys gfxinfo <pkg>`."""
    out: dict = {}
    if m := TOTAL_FRAMES_RE.search(text):
        out["frames"] = int(m.group(1))
    if m := re.search(r"Janky frames: (\d+) \(([\d.]+)%\)", text):
        out["janky_frames"], out["janky_pct"] = int(m.group(1)), float(m.group(2))
    for p in (50, 90, 95, 99):
        if m := re.search(rf"{p}th percentile: (\d+)ms", text):
            out[f"p{p}_ms"] = int(m.group(1))
    for key, label in (
        ("slow_ui_thread", "Slow UI thread"),
        ("deadline_missed", "Frame deadline missed"),
        ("high_input_latency", "High input latency"),
    ):
        if m := re.search(rf"Number {label}: (\d+)", text):
            out[key] = int(m.group(1))
    return out


def parse_framestats(text: str) -> list[dict]:
    """PROFILEDATA rows of `dumpsys gfxinfo <pkg> framestats` (columns vary by Android version)."""
    frames: list[dict] = []
    for block in re.findall(r"---PROFILEDATA---\s*(.*?)\s*---PROFILEDATA---", text, re.DOTALL):
        lines = [ln.strip().rstrip(",") for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        header = lines[0].split(",")
        for ln in lines[1:]:
            vals = ln.split(",")
            if len(vals) < len(header):
                continue
            row = dict(zip(header, vals, strict=False))
            try:
                f = {
                    "flags": int(row.get("Flags", 0)),
                    "start": int(row["IntendedVsync"]),
                    "end": int(row["FrameCompleted"]),
                    "deadline": int(row.get("FrameDeadline") or 0),
                    "interval": int(row.get("FrameInterval") or 16_666_666),
                }
            except (KeyError, ValueError):
                continue
            if f["end"] > f["start"] > 0:
                frames.append(f)
    return frames


def parse_am_start(text: str) -> dict:
    out: dict = {}
    for key in ("TotalTime", "WaitTime"):
        if m := re.search(rf"{key}: (\d+)", text):
            out[key] = int(m.group(1))
    if m := re.search(r"LaunchState: (\w+)", text):
        out["LaunchState"] = m.group(1)
    return out
