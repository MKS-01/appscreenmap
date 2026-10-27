"""The audits every crawl can show without another tool: coverage, stability, accessibility and performance.

A port of the viewer's `apps/viewer/src/insights/builtin.ts`, so the engine writes them as `audits/<id>.json` like
every other audit and the report reads one shape. Keep the two in step until the viewer drops its own builders.
Deliberate differences (2026-10-28, handed to the web session): an error caps the status at warn, crashes are keyed by
screen, and a11y applies notes.json triage and lists only the screens still open.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from appscreenmap.core import __version__
from appscreenmap.core.model import load_map

from .sources import refs

BUILTIN = ("coverage", "stability", "a11y", "perf")
DISMISSED = ("wontfix", "false_positive")
MAX_ELEMENTS = 20  # per a11y finding: enough to find the code, not the whole list


def capped(status: str, findings: list[dict]) -> str:
    """An audit holding an error never reads as passing, whatever its score (decided 2026-10-28)."""
    return "warn" if status == "pass" and any(f.get("severity") == "error" for f in findings) else status


def status_from_score(score: float | None) -> str:
    return "info" if score is None else "pass" if score >= 90 else "warn" if score >= 70 else "fail"


def _pct(n: int, d: int) -> int:
    return round(100 * n / d) if d > 0 else 0


def _plural(n: int, w: str) -> str:
    return f"{n} {w}{'' if n == 1 else 's'}"


def _short(activity: str | None) -> str:
    return re.sub(r"^.*\.", "", activity) if activity else "—"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _shell(audit: str, title: str, **kw) -> dict:
    return {
        "schema": 1,
        "audit": audit,
        "title": title,
        "tool": f"appscreenmap {__version__}",
        "generated_at": _now(),
        "source": "run",
        "metrics": [],
        "charts": [],
        "findings": [],
        "refs": [],
        **kw,
    }


def not_run(audit: str, title: str, how: str) -> dict:
    return _shell(audit, title, source="none", status="not_run", score=None, summary=how)


# ── coverage ─────────────────────────────────────────────────────────────────


def coverage(data: dict) -> dict:
    run, st = data["run"], data["stats"]
    app = [s for s in data["screens"] if s["kind"] == "app"]
    el = st.get("elements") or {}
    tried = el.get("done") or 0
    open_ = (el.get("pending") or 0) + (el.get("failed") or 0) + (el.get("unreachable") or 0)
    score = _pct(tried, tried + open_) if tried + open_ else None
    max_steps = (run.get("config") or {}).get("max_steps")
    budget_hit = max_steps is not None and (run.get("steps") or 0) >= int(max_steps)

    findings = []
    declared = (run.get("app") or {}).get("activities") or []
    visited = set(st.get("activities_visited") or [])
    for a in (a for a in declared if a not in visited):
        findings.append(
            {
                "id": f"activity-missed::{a}",
                "severity": "warning",
                "category": "Activities",
                "title": f"{_short(a)} was never reached",
                "detail": f"{a} is declared in the manifest but no crawled screen ran in it.",
                "fix": "Raise --max-steps, add test credentials for gated areas, or check whether the activity is still used.",
            }
        )
    for s in app:
        els = s.get("elements") or []
        pending = sum(e.get("status") == "pending" for e in els)
        if pending:
            findings.append(
                {
                    "id": f"untried::{s['id']}",
                    "severity": "warning",
                    "category": "Untried actions",
                    "screen": s["id"],
                    "title": f"{_plural(pending, 'action')} never tried on {s['title']}",
                    "detail": f"The crawl stopped at its {max_steps}-step budget."
                    if budget_hit
                    else "The crawl ended before it could try them (time budget, or the screen became unreachable).",
                    **({"fix": "Re-run with a higher --max-steps."} if budget_hit else {}),
                }
            )
        for e in els:
            if e.get("status") in ("failed", "unreachable"):
                findings.append(
                    {
                        "id": f"nav::{s['id']}::{e['id']}",
                        "severity": "warning",
                        "category": "Navigation",
                        "screen": s["id"],
                        "title": f"“{e.get('label')}” "
                        + (
                            "couldn't be found to tap"
                            if e["status"] == "failed"
                            else "is on a screen the crawler couldn't return to"
                        ),
                    }
                )
            elif e.get("status") == "blocked":
                findings.append(
                    {
                        "id": f"blocked::{s['id']}::{e['id']}",
                        "severity": "info",
                        "category": "Blocked for safety",
                        "screen": s["id"],
                        "title": f"“{e.get('label')}” was never tapped",
                        "detail": "Its label matches blocked_text (logout, delete, pay, …).",
                    }
                )

    depth = Counter(s.get("depth", 0) for s in app)
    cov = st.get("activity_coverage")
    summary = f"{tried} of {tried + open_} actions tried"
    if declared:
        summary += f" · {len(visited)} of {len(declared)} activities"
    if budget_hit:
        summary += " · stopped at the step budget"
    return _shell(
        "coverage",
        "Crawl coverage",
        status=capped(status_from_score(score), findings),
        score=score,
        score_note="Share of discovered actions the crawl actually tried (blocked and pattern-skipped ones excluded).",
        **({"status_label": "Partial"} if budget_hit and score is not None and score < 90 else {}),
        summary=summary,
        metrics=[
            {"label": "screens", "value": st.get("screens", 0)},
            {"label": "transitions", "value": st.get("transitions", 0)},
            {"label": "max depth", "value": st.get("max_depth", 0)},
            {
                "label": "activity coverage",
                "value": f"{round(cov * 100)}%" if cov is not None else "—",
                **(
                    {"tone": "good" if cov >= 0.9 else "warn"}
                    if cov is not None
                    else {"hint": "Needs aapt2 to read declared activities from the APK"}
                ),
            },
            {
                "label": "untried actions",
                "value": el.get("pending") or 0,
                "tone": "warn" if el.get("pending") else "good",
            },
            {"label": "steps", "value": run.get("steps") or "—"},
        ],
        charts=[
            {
                "type": "columns",
                "title": "Screens by depth",
                "note": "Taps from launch",
                "data": [{"label": str(d), "value": n} for d, n in sorted(depth.items())],
            }
        ],
        findings=findings,
    )


# ── stability ────────────────────────────────────────────────────────────────


def stability(data: dict) -> dict:
    events = data.get("events") or []
    titles = {s["id"]: s["title"] for s in data["screens"]}
    crashes = [e for e in events if e.get("type") == "crash"]
    nav_failed = [e for e in events if e.get("type") == "nav_failed"]
    restarts = [e for e in events if e.get("type") == "restart"]
    score = max(0, 100 - 30 * len(crashes) - 2 * len(nav_failed))
    types = Counter(e.get("type") for e in events)
    tone = {"crash": "bad", "nav_failed": "warn"}

    if crashes:
        summary = " · ".join(
            f"crash at step {e.get('step')}"
            + (f" on {titles.get(e['screen'], e['screen'])}" if e.get("screen") else "")
            + (" · logcat attached" if e.get("log") else "")
            for e in crashes
        )
        summary = summary[0].upper() + summary[1:]
    else:
        summary = f"No crashes in {data['run'].get('steps') or 'the'} steps" + (
            f" · {_plural(len(nav_failed), 'failed navigation')}." if nav_failed else "."
        )
    # Keyed by screen, not step: the same crash at another step on a re-crawl stays the same fix-list task.
    nth: Counter = Counter()
    crash_findings = []
    for e in crashes:
        where = e.get("screen") or "app"
        crash_findings.append(
            {
                "id": f"crash::{where}::{nth[where]}",
                "severity": "error",
                "category": "Crashes",
                **({"screen": e["screen"]} if e.get("screen") else {}),
                "title": f"Crash on {titles.get(e['screen'], e['screen'])}" if e.get("screen") else "Crash",
                "detail": f"At step {e.get('step')}: {e.get('detail')}"
                + (f" · logcat: {e['log']}" if e.get("log") else ""),
                "fix": "Open the logcat file for the stack trace; replay the screen's reach path to reproduce.",
            }
        )
        nth[where] += 1
    findings = crash_findings + [
        {
            "id": f"nav-failed::{e.get('step')}::{i}",
            "severity": "warning",
            "category": "Navigation",
            **({"screen": e["screen"]} if e.get("screen") else {}),
            "title": f"Couldn't navigate back to a screen at step {e.get('step')}",
            "detail": e.get("detail"),
        }
        for i, e in enumerate(nav_failed)
    ]
    return _shell(
        "stability",
        "Stability",
        status="fail" if crashes else status_from_score(score),
        score=score,
        score_note="100, minus 30 per crash and 2 per failed navigation during the crawl.",
        summary=summary,
        metrics=[
            {"label": "crashes", "value": len(crashes), "tone": "bad" if crashes else "good"},
            {
                "label": "failed navigations",
                "value": len(nav_failed),
                "tone": "warn" if nav_failed else "good",
            },
            {"label": "app restarts", "value": len(restarts)},
            {"label": "events", "value": len(events)},
        ],
        charts=[
            {
                "type": "bars",
                "title": "Run events by type",
                "data": [
                    {"label": t.replace("_", " ", 1), "value": n, **({"tone": tone[t]} if t in tone else {})}
                    for t, n in types.items()
                ],
            }
        ]
        if types
        else [],
        findings=findings,
        refs=refs("androidVitals"),
    )


# ── accessibility (a11y.json) ────────────────────────────────────────────────


def _slug(s: str) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", re.sub(r"[()]", "", s.lower())))


def a11y(data: dict, a11y_file: dict | None, triage: dict | None = None) -> dict:
    """`triage` is notes.json's `a11y` map; it wins over the a11y.json snapshot, so triage counts without a re-run."""
    if not a11y_file:
        return not_run(
            "a11y", "Accessibility (WCAG 2.2)", "Run `appscreenmap a11y <run>` to write a11y.json."
        )
    app = [s for s in data["screens"] if s["kind"] == "app"]
    issues = [
        {**i, "triage": (triage or {}).get(i.get("key"), {}).get("status") or i.get("triage") or "open"}
        for i in a11y_file.get("issues") or []
    ]
    rules = a11y_file.get("rules") or {}
    summary_ = a11y_file.get("summary") or {}
    # App-level issues (orientation lock, inconsistent navigation) aren't tied to one screen: 10 points each.
    serious = [i for i in issues if i.get("severity") != "info"]
    app_wide = sum(i.get("screen") == "app" for i in serious)
    flagged = {i.get("screen") for i in serious}
    score = max(0, _pct(sum(s["id"] not in flagged for s in app), len(app)) - 10 * app_wide) if app else None
    sev = Counter(i.get("severity") for i in issues)

    by_rule: dict[str, list[dict]] = defaultdict(list)
    for i in issues:
        by_rule[i["rule"]].append(i)
    findings = []
    for rule, group in by_rule.items():
        r = rules.get(rule)
        # Where to fix: the issues still open; a fully dismissed rule keeps them all and carries its triage.
        live = [i for i in group if i.get("triage") not in DISMISSED] or group
        screens = list(dict.fromkeys(i["screen"] for i in live if i.get("screen") != "app"))
        triage = {i.get("triage") or "open" for i in group}
        f = {
            "id": f"a11y::{rule}",
            "severity": (r or {}).get("severity") or group[0].get("severity"),
            "title": f"{r['name']} ({_plural(len(live), 'issue')})" if r else rule,
            "detail": (f"On {_plural(len(screens), 'screen')}. " if screens else "")
            + ((r or {}).get("why") or ""),
        }
        if r:
            f["category"] = f"{r['sc']} · Level {r['level']}"
            f["fix"] = r.get("fix")
            f["refs"] = [
                {
                    "title": f"WCAG 2.2 · {r['sc']} {r['name']}",
                    "url": f"https://www.w3.org/TR/WCAG22/#{_slug(r['name'])}",
                    "publisher": "W3C",
                }
            ]
        if screens:
            f["screen"], f["screens"] = screens[0], screens
        els: dict[tuple, list | None] = {}
        for i in live:
            if i.get("screen") != "app":
                k = (i["screen"], i.get("rid") or "", i.get("label") or "")
                if not els.get(k) or not any(els[k]):  # a real box wins over a page-level [0,0,0,0]
                    els[k] = i.get("bounds")
        if els:
            f["elements"] = [
                {"screen": s, "rid": r, "label": lb, **({"bounds": b} if b else {})}
                for (s, r, lb), b in list(els.items())[:MAX_ELEMENTS]
            ]
        if len(triage) == 1 and (t := triage.pop()) != "open":
            f["triage"] = t
        findings.append(f)

    by_sc = summary_.get("by_criterion") or {}
    by_level = summary_.get("by_level") or {}
    top = max(by_sc.items(), key=lambda kv: kv[1])[0] if by_sc else None
    triaged = sum((i.get("triage") or "open") != "open" for i in issues)
    return _shell(
        "a11y",
        "Accessibility (WCAG 2.2)",
        status=capped(status_from_score(score), findings),
        score=score,
        score_note="Share of app screens with no error or warning, minus 10 per app-wide error or warning (e.g. a locked orientation).",
        summary=f"{_plural(len(issues), 'issue')} across {len(by_sc)} success criteria"
        + (f" · most: {top}" if top else ""),
        metrics=[
            {"label": "errors", "value": sev["error"], "tone": "bad" if sev["error"] else "good"},
            {"label": "warnings", "value": sev["warning"], "tone": "warn" if sev["warning"] else "good"},
            {"label": "suggestions", "value": sev["info"]},
            {"label": "level A", "value": by_level.get("A", 0)},
            {"label": "level AA", "value": by_level.get("AA", 0)},
            {"label": "triaged", "value": f"{triaged}/{len(issues)}"},
        ],
        charts=[
            {
                "type": "bars",
                "title": "Issues by success criterion",
                "data": [{"label": k, "value": v} for k, v in sorted(by_sc.items(), key=lambda kv: -kv[1])],
            },
            {
                "type": "split",
                "title": "Issues by severity",
                "data": [
                    {"label": "error", "value": sev["error"], "tone": "bad"},
                    {"label": "warning", "value": sev["warning"], "tone": "warn"},
                    {"label": "info", "value": sev["info"], "tone": "info"},
                ],
            },
        ],
        findings=findings,
        refs=refs("wcag22", "androidA11y"),
    )


# ── performance (perf.json) ──────────────────────────────────────────────────


def _perf_tone(rating: str) -> str:
    return "bad" if rating == "slow" else "warn" if rating == "needs work" else "good"


def perf(data: dict, perf_file: dict | None) -> dict:
    if not perf_file:
        return not_run(
            "perf", "Performance", "Crawl with load measurement on (the default) to write perf.json."
        )
    if not perf_file.get("screens"):
        ios = (data["run"].get("device") or {}).get("platform") == "ios"
        return not_run(
            "perf",
            "Performance",
            "Load times weren't measured in this crawl"
            + (" (iOS has no frame counters wired yet; planned)." if ios else "."),
        )
    budget = perf_file.get("budget_ms", 1000)
    screens = sorted(perf_file["screens"], key=lambda s: -s["median_ms"])
    good = sum(_perf_tone(s["rating"]) == "good" for s in screens)
    score = _pct(good, len(screens))
    over = [s for s in screens if s["median_ms"] > budget]

    # Same rule as perf.py: > 10% slow frames, and at least 30 frames so a 2-frame transition can't count.
    def janky(s):
        return s.get("frames", 0) >= 30 and s.get("janky_pct", 0) > 10

    jank = sorted((s for s in screens if janky(s)), key=lambda s: -s["janky_pct"])
    startup = perf_file.get("startup") or {}
    parts = [f"{screens[0]['title']} loads in {screens[0]['median_ms']:,} ms"]
    if jank:
        parts.append(f"{jank[0]['title']} {round(jank[0]['janky_pct'])}% janky frames")
    if startup.get("median_ms") is not None:
        parts.append(f"cold start {startup['median_ms']} ms")
    findings = []
    for s in screens:
        if _perf_tone(s["rating"]) == "good" and not janky(s):
            continue
        frozen = s.get("frozen_frames") or 0
        findings.append(
            {
                "id": f"perf::{s['screen']}",
                "severity": "error"
                if s["rating"] == "slow"
                else "warning"
                if s["rating"] == "needs work"
                else "info",
                "category": "Load time" if s["median_ms"] > budget else "Jank",
                "screen": s["screen"],
                "title": f"{s['title']}: {s['median_ms']} ms"
                + (f", {s['janky_pct']}% janky frames" if s.get("frames", 0) >= 30 else ""),
                "detail": f"Rated “{s['rating']}”. Budget {budget} ms."
                + (f" {_plural(frozen, 'frozen frame')}." if frozen else ""),
                "fix": "Profile the transition (Perfetto) and move work off the main thread or behind a placeholder.",
            }
        )
    return _shell(
        "perf",
        "Performance",
        status=capped(status_from_score(score), findings),
        score=score,
        score_note="Share of measured screens rated good (load under budget, little jank).",
        summary=" · ".join(parts),
        metrics=[
            {
                "label": "cold start (median)",
                "value": startup.get("median_ms", "—"),
                **({"unit": "ms"} if startup else {}),
            },
            {"label": "screens measured", "value": len(screens)},
            {"label": "over budget", "value": len(over), "tone": "bad" if over else "good"},
            {"label": "janky screens", "value": len(jank), "tone": "warn" if jank else "good"},
            {"label": "slowest", "value": screens[0]["median_ms"], "unit": "ms", "hint": screens[0]["title"]},
        ],
        charts=[
            {
                "type": "bars",
                "title": "Load time per screen (median)",
                "unit": "ms",
                "budget": budget,
                "budgetLabel": f"{budget} ms budget",
                "data": [
                    {
                        "label": s["title"],
                        "value": s["median_ms"],
                        "tone": _perf_tone(s["rating"]),
                        "screen": s["screen"],
                        "hint": f"{s.get('janky_pct', 0)}% of {s.get('frames', 0)} frames janky",
                    }
                    for s in screens
                ],
            }
        ],
        findings=findings,
        refs=refs("androidVitals"),
    )


# ── files ────────────────────────────────────────────────────────────────────


def _read(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def build_builtin(run: Path, data: dict | None = None) -> dict[str, dict]:
    run = Path(run)
    data = data or load_map(run)
    return {
        "coverage": coverage(data),
        "stability": stability(data),
        "a11y": a11y(data, _read(run / "a11y.json"), (_read(run / "notes.json") or {}).get("a11y")),
        "perf": perf(data, _read(run / "perf.json")),
    }


def write_builtin(run: Path, data: dict | None = None) -> dict[str, dict]:
    """Write the four built-in audits into `<run>/audits/`, fresh from the run's files."""
    audits = build_builtin(run, data)
    d = Path(run) / "audits"
    d.mkdir(exist_ok=True)
    for aid, audit in list(audits.items()):
        p = d / f"{aid}.json"
        other = _read(p) if p.is_file() else None
        # A file another tool wrote under a built-in id wins, as everywhere else; ours is refreshed.
        if other and not str(other.get("tool") or "").startswith("appscreenmap"):
            audits[aid] = other
            continue
        p.write_text(json.dumps(audit, indent=1, ensure_ascii=False) + "\n")
    return audits
