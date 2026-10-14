"""Navigation performance report: per-screen load times, slow transitions, jank and cold start.

Reads the timings the crawl recorded in map.json (measured by `appscreenmap.crawler.timing`).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path

from appscreenmap.core.model import load_map, write_json_atomic
from appscreenmap.drivers.dumpsys import FROZEN_FRAME_MS

MIN_JANK_FRAMES = 30  # fewer frames than this are too few to call a screen janky


def _jank(sample: dict) -> tuple[int, int]:
    """(frames, janky) for a timing sample, preferring the platform's gfxinfo counts."""
    st = sample.get("stats") or {}
    if "frames" in st and "janky_frames" in st:
        return st["frames"], st["janky_frames"]
    return sample.get("frames", 0), sample.get("janky_frames", 0)


def _pct(values: list[int], q: float) -> int:
    s = sorted(values)
    return s[min(len(s) - 1, round(q * (len(s) - 1)))]


def summarize(run_dir: str | Path, budget_ms: int = 1000, write: bool = True) -> dict:
    """Per-screen load times (arrivals by navigation, not back/scroll), slow transitions, startup."""
    run_dir = Path(run_dir)
    data = load_map(run_dir)
    screens = {s["id"]: s for s in data["screens"]}
    per_screen: dict[str, list[dict]] = defaultdict(list)
    transitions = []
    for t in data["transitions"]:
        samples = t.get("timings") or []
        if not samples or t.get("inferred"):
            continue
        loads = [s["load_ms"] for s in samples if s.get("load_ms") is not None]
        if not loads:
            continue
        row = {
            "from": t["from"],
            "to": t["to"],
            "label": t["label"],
            "action": t["action"],
            "kind": t["kind"],
            "samples": len(loads),
            "median_ms": round(statistics.median(loads)),
            "max_ms": max(loads),
            "unsettled": sum(1 for s in samples if not s.get("settled", True)),
            "janky_frames": sum(_jank(s)[1] for s in samples),
            "frozen_frames": sum(s.get("frozen_frames", 0) for s in samples),
            "waited_for_loading": any(s.get("waited_for_loading") for s in samples),
        }
        transitions.append(row)
        if t["kind"] not in ("back", "up"):
            per_screen[t["to"]].extend(samples)

    screen_rows = []
    for sid, samples in per_screen.items():
        loads = [s["load_ms"] for s in samples if s.get("load_ms") is not None]
        frames = sum(_jank(s)[0] for s in samples)
        janky = sum(_jank(s)[1] for s in samples)
        median = round(statistics.median(loads))
        screen_rows.append(
            {
                "screen": sid,
                "title": screens.get(sid, {}).get("title", sid),
                "samples": len(loads),
                "median_ms": median,
                "p90_ms": _pct(loads, 0.9),
                "max_ms": max(loads),
                "frames": frames,
                "janky_pct": round(100 * janky / frames, 1) if frames else None,
                "frozen_frames": sum(s.get("frozen_frames", 0) for s in samples),
                "unsettled": sum(1 for s in samples if not s.get("settled", True)),
                "waited_for_loading": any(s.get("waited_for_loading") for s in samples),
                "rating": "slow"
                if median > budget_ms * 2.5
                else "needs work"
                if median > budget_ms
                else "ok",
            }
        )
    screen_rows.sort(key=lambda r: -r["median_ms"])
    transitions.sort(key=lambda r: -r["max_ms"])

    startup = (data.get("perf") or {}).get("startup") or []
    cold = [s["TotalTime"] for s in startup if s.get("TotalTime") and s.get("LaunchState", "COLD") == "COLD"]
    findings = []
    for r in screen_rows:
        if r["rating"] != "ok":
            findings.append(
                f"{r['screen']} '{r['title']}' loads in {r['median_ms']} ms (median, budget {budget_ms} ms)"
            )
        if r["frozen_frames"]:
            findings.append(
                f"{r['screen']} '{r['title']}' had {r['frozen_frames']} frozen frame(s) (> {FROZEN_FRAME_MS} ms)"
            )
        if r["janky_pct"] and r["janky_pct"] > 10 and r["frames"] >= MIN_JANK_FRAMES:
            findings.append(f"{r['screen']} '{r['title']}' renders janky: {r['janky_pct']}% slow frames")
        if r["unsettled"]:
            findings.append(
                f"{r['screen']} '{r['title']}' never stopped drawing within the timeout "
                "(continuous animation or polling UI)"
            )
    if cold and statistics.median(cold) > 5000:
        findings.append(
            f"cold start {statistics.median(cold):.0f} ms (median) exceeds Android vitals' 5 s threshold"
        )

    report = {
        "run": data["run"]["id"],
        "budget_ms": budget_ms,
        "animations": "off" if data["run"].get("config", {}).get("disable_animations", True) else "on",
        "startup": {
            "samples": len(cold),
            "median_ms": round(statistics.median(cold)) if cold else None,
            "max_ms": max(cold) if cold else None,
        },
        "screens": screen_rows,
        "transitions": transitions,
        "findings": findings,
    }
    if write:
        write_json_atomic(run_dir / "perf.json", report)
    return report


def format_perf(rep: dict, top: int = 12) -> str:
    st = rep["startup"]
    lines = [
        f"Navigation performance for {rep['run']} (budget {rep['budget_ms']} ms, animations {rep['animations']})",
        f"  cold start: {st['median_ms']} ms median, {st['max_ms']} ms max over {st['samples']} launch(es)"
        if st["samples"]
        else "  cold start: not measured",
    ]
    if not rep["screens"]:
        lines.append(
            "  no load timings in this run (crawled before metrics existed, or measure_load = false)"
        )
        return "\n".join(lines)
    lines.append("  screens, slowest first (median / p90 / max ms, samples):")
    for r in rep["screens"][:top]:
        flag = {"slow": "🔴", "needs work": "🟠", "ok": "🟢"}[r["rating"]]
        extra = []
        if r["janky_pct"] is not None and r["frames"] >= MIN_JANK_FRAMES:
            extra.append(f"{r['janky_pct']}% janky")
        if r["frozen_frames"]:
            extra.append(f"{r['frozen_frames']} frozen")
        if r["waited_for_loading"]:
            extra.append("loading indicator")
        if r["unsettled"]:
            extra.append("never settled")
        lines.append(
            f"   {flag} {r['screen']:>5} {r['title'][:28]!r:30} {r['median_ms']:>5} / {r['p90_ms']:>5} / "
            f"{r['max_ms']:>5}  ×{r['samples']}  {', '.join(extra)}"
        )
    lines.append("  slowest transitions:")
    for t in rep["transitions"][:5]:
        lines.append(f"     {t['from']} → {t['to']}  {t['label'][:30]!r:32} {t['max_ms']} ms max")
    lines.append("  findings:" if rep["findings"] else "  findings: none")
    lines += [f"    • {f}" for f in rep["findings"]]
    return "\n".join(lines)
