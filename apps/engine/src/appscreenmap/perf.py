"""Navigation performance: how long a screen takes to load after an action, and how smoothly it renders.

How it is measured (no app instrumentation needed):
- Before an action, the app's frame stats are reset (`dumpsys gfxinfo <pkg> reset`).
- After the action, the app's rendered-frame counter is polled until it stops changing for
  `quiet_ms`. The app has finished drawing: the screen is *visually settled*.
- If the settled screen still shows a loading indicator, we wait for the next burst of frames
  (the content arriving) and settle again.
- The load time is the host-measured time from the action to the last frame change. Frame stats
  (`framestats`) give the precise on-device render span and jank for the same window.
- App start uses `am start -W` (TotalTime) on every cold relaunch.

The resolution is one poll (~50–100 ms over adb). Numbers are for comparing screens and builds on
the same device, not absolute truths. Animations follow the crawl setting (`disable_animations`):
off gives content-only times, on gives what a user sees.
"""

from __future__ import annotations

import re
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from appscreenmap.core.model import load_map, write_json_atomic

_LOADING_RE = re.compile(r"\b(loading|please wait|fetching|syncing)\b", re.IGNORECASE)
FROZEN_FRAME_MS = 700
MIN_JANK_FRAMES = 30  # fewer frames than this are too few to call a screen janky  # Android vitals: a frame taking > 700 ms is "frozen"


@dataclass
class Timing:
    load_ms: int | None  # action → screen visually settled (host clock)
    settled: bool  # False: the app never stopped drawing within the timeout
    render_ms: int | None = None  # first → last frame of the window (device clock, from framestats)
    frames: int = 0
    janky_frames: int = 0
    frozen_frames: int = 0
    p90_frame_ms: float | None = None
    max_frame_ms: float | None = None
    waited_for_loading: bool = False
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            k: v
            for k, v in self.__dict__.items()
            if v not in (None, {}, False) or k in ("settled", "load_ms")
        }
        return d


def frame_metrics(frames: list[dict]) -> dict:
    if not frames:
        return {}
    durations = sorted((f["end"] - f["start"]) / 1e6 for f in frames)
    span = (max(f["end"] for f in frames) - min(f["start"] for f in frames)) / 1e6
    return {
        "render_ms": round(span),
        "frames": len(frames),
        # Android's definition: janky = completed after its deadline (FrameDeadline, Android 12+);
        # older versions: took longer than one refresh interval.
        "janky_frames": sum(
            1
            for f in frames
            if (
                f["end"] > f["deadline"]
                if f.get("deadline")
                else f["end"] - f["start"] > f.get("interval", 16_666_666)
            )
        ),
        "frozen_frames": sum(1 for d in durations if d > FROZEN_FRAME_MS),
        "p90_frame_ms": round(durations[min(len(durations) - 1, int(len(durations) * 0.9))], 1),
        "max_frame_ms": round(durations[-1], 1),
    }


def has_loading_indicator(root) -> bool:
    """A visible progress indicator or 'Loading…' text on the screen."""
    for n in root.walk():
        if n.area <= 0:
            continue
        if "ProgressBar" in n.cls or "CircularProgress" in n.cls or "LinearProgress" in n.cls:
            return True
        if _LOADING_RE.search(n.text or "") or _LOADING_RE.search(n.desc or ""):
            return True
    return False


# ── measuring ────────────────────────────────────────────────────────────────


class LoadMeter:
    def __init__(
        self, driver, package: str, quiet_ms: int = 400, timeout_s: float = 10.0, min_wait_s: float = 0.15
    ):
        self.d = driver
        self.pkg = package
        self.quiet = quiet_ms / 1000
        self.timeout = timeout_s
        self.min_wait = min_wait_s
        self.t0: float | None = None

    def begin(self) -> None:
        """Call right before the action."""
        self.d.gfx_reset(self.pkg)
        self.t0 = time.monotonic()

    def wait_settled(self, until_new_frames: bool = False) -> tuple[bool, float]:
        """Poll the frame counter until it stops changing. Returns (settled, seconds from t0 to last change)."""
        assert self.t0 is not None, "begin() first"
        time.sleep(self.min_wait)
        last = self.d.frames_rendered(self.pkg)
        last_change = time.monotonic() if (last or 0) > 0 else self.t0
        start_count = last
        while True:
            now = time.monotonic()
            if now - self.t0 > self.timeout:
                return False, last_change - self.t0
            count = self.d.frames_rendered(self.pkg)
            now = time.monotonic()
            if count != last:
                last, last_change = count, now
                continue
            waiting_for_burst = until_new_frames and count == start_count
            if not waiting_for_burst and now - last_change >= self.quiet:
                return True, last_change - self.t0

    def finish(self, settled: bool, seconds: float, waited_for_loading: bool = False) -> Timing:
        t = Timing(load_ms=round(seconds * 1000), settled=settled, waited_for_loading=waited_for_loading)
        try:
            t.stats = self.d.gfx_summary(self.pkg)
            fm = frame_metrics(self.d.gfx_framestats(self.pkg))
        except Exception:  # noqa: BLE001 — metrics are best effort; never break a crawl
            fm = {}
        for k, v in fm.items():
            setattr(t, k, v)
        # Prefer the platform's own counts for the same window when gfxinfo reports them.
        if "janky_frames" in t.stats and "frames" in t.stats:
            t.frames, t.janky_frames = t.stats["frames"], t.stats["janky_frames"]
        return t


# ── summarizing a run ────────────────────────────────────────────────────────


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
