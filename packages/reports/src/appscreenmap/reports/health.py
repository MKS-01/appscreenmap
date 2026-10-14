"""Run health report: how well did a crawl spend its steps, and where did it go wrong?

Used by `appscreenmap report` and by the maintenance skills to spot exploration problems.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from appscreenmap.core.analyzer import jaccard
from appscreenmap.core.model import load_map
from appscreenmap.drivers.device import caveats, describe

NEAR_DUPLICATE = 0.6  # screens this similar (same activity) may be one screen split in two
CROWDED = 60  # a screen with more elements than this may be several screens merged


def _trace(run_dir: Path) -> list[dict]:
    p = run_dir / "trace.jsonl"
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def build_report(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    data = load_map(run_dir)
    trace = _trace(run_dir)
    run, stats = data["run"], data["stats"]
    screens = [s for s in data["screens"] if s["kind"] == "app"]
    steps = run.get("steps") or 0

    explored = [t for t in trace if t.get("explore")]
    effects = Counter(t.get("effect") or t.get("result") for t in explored)
    noop_by_key: dict[str, set[str]] = defaultdict(set)
    labels: dict[str, str] = {}
    for t in explored:
        if t.get("effect") == "same_screen" and t.get("action") != "scroll":
            noop_by_key[t["key"]].add(t["screen"])
            labels[t["key"]] = t.get("label", "")
    repeated_noops = sorted(
        ({"key": k, "label": labels[k], "screens": sorted(v)} for k, v in noop_by_key.items() if len(v) >= 3),
        key=lambda r: -len(r["screens"]),
    )

    near_dupes = []
    for i, a in enumerate(screens):
        for b in screens[i + 1 :]:
            if a.get("activity") != b.get("activity") or b.get("variant_of") == a["id"]:
                continue
            sim = jaccard(frozenset(a.get("tokens", [])), frozenset(b.get("tokens", [])))
            if sim >= NEAR_DUPLICATE:
                near_dupes.append(
                    {"a": a["id"], "b": b["id"], "titles": [a["title"], b["title"]], "sim": round(sim, 2)}
                )

    events = Counter(e["type"] for e in data.get("events", []))
    status = Counter(e["status"] for s in screens for e in s.get("elements", []))
    unexplored = [
        {"id": s["id"], "title": s["title"], "pending": n}
        for s in screens
        if (n := sum(1 for e in s.get("elements", []) if e["status"] in ("pending", "unreachable")))
    ]
    left_app = [t for t in explored if t.get("effect") == "left_app"]

    findings = []
    if steps and stats["screens"] and steps / stats["screens"] > 12:
        findings.append(
            f"{steps / stats['screens']:.1f} steps per screen; exploration is spending a lot per discovery"
        )
    if repeated_noops:
        findings.append(
            f"{len(repeated_noops)} element(s) did nothing on 3+ screens; candidates for global inference"
        )
    if near_dupes:
        findings.append(
            f"{len(near_dupes)} near-duplicate screen pair(s); possible over-splitting of screen identity"
        )
    crowded = [s["id"] for s in screens if len(s.get("elements", [])) > CROWDED]
    if crowded:
        findings.append(f"crowded screens {crowded}; possible over-merging or unbounded list growth")
    if events["nav_failed"]:
        findings.append(f"{events['nav_failed']} navigation failure(s); routing or replay is unreliable")
    if events["restart"] > max(3, steps // 10):
        findings.append(f"{events['restart']} restarts; the app keeps escaping or routes keep failing")
    if left_app:
        findings.append(f"{len(left_app)} action(s) left the app: {[t['label'] for t in left_app][:5]}")
    if effects.get("not_found"):
        findings.append(
            f"{effects['not_found']} element(s) not found when revisiting; unstable element keys?"
        )
    if events["crash"]:
        findings.append(f"{events['crash']} app crash(es); see crashes/")
    if run.get("status") == "running":
        findings.append("status is still 'running': the crawl is in progress or was killed")

    return {
        "run": run["id"],
        "status": run.get("status"),
        "device": describe(run.get("device") or {}),
        "device_caveats": caveats(run.get("device") or {}),
        "stop_reason": run.get("stop_reason"),
        "steps": steps,
        "elapsed_s": run.get("elapsed_s"),
        "seconds_per_step": round(run["elapsed_s"] / steps, 2) if steps and run.get("elapsed_s") else None,
        "screens": stats["screens"],
        "transitions": stats["transitions"],
        "steps_per_screen": round(steps / stats["screens"], 1) if stats["screens"] else None,
        "activity_coverage": stats.get("activity_coverage"),
        "effects": dict(effects),
        "element_status": dict(status),
        "events": dict(events),
        "repeated_noops": repeated_noops,
        "near_duplicates": near_dupes,
        "unexplored": unexplored,
        "findings": findings,
    }


def format_report(r: dict) -> str:
    lines = [
        f"Run {r['run']}  [{r['status']}]  {r['stop_reason'] or ''}",
        f"  {r['screens']} screens, {r['transitions']} transitions, {r['steps']} steps"
        + (
            f" ({r['seconds_per_step']} s/step, {r['steps_per_screen']} steps/screen)"
            if r["steps_per_screen"]
            else ""
        ),
        f"  device: {r['device']}",
        f"  effects: {r['effects']}",
        f"  elements: {r['element_status']}",
        f"  events: {r['events']}",
    ]
    if r["activity_coverage"] is not None:
        lines.append(f"  activity coverage: {r['activity_coverage']:.0%}")
    if r["repeated_noops"]:
        lines.append("  repeated no-op taps:")
        lines += [f"    {x['label']!r} on {', '.join(x['screens'])}" for x in r["repeated_noops"][:8]]
    if r["near_duplicates"]:
        lines.append("  near-duplicate screens:")
        lines += [f"    {x['a']} ~ {x['b']} {x['titles']} sim={x['sim']}" for x in r["near_duplicates"][:8]]
    if r["unexplored"]:
        lines.append(
            "  screens with unexplored elements: "
            + ", ".join(f"{u['id']}({u['pending']})" for u in r["unexplored"])
        )
    if r["device_caveats"]:
        lines.append("  device caveats:")
        lines += [f"    ! {c}" for c in r["device_caveats"]]
    lines.append("  findings:" if r["findings"] else "  findings: none 🎉")
    lines += [f"    • {f}" for f in r["findings"]]
    return "\n".join(lines)
