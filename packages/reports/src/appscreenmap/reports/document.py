"""One report for a canvas, built from every `audits/<id>.json` in the shape of docs/MAP_SCHEMA.md.

`build_document` makes a format-free model (cover, summary, conditions, one section per audit, appendix) that each
renderer (`markdown`, `htmldoc`, `fixes`) only lays out. A new audit gets into the report by writing its file.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from appscreenmap.core import __version__
from appscreenmap.core.model import load_map
from appscreenmap.drivers.device import describe
from appscreenmap.drivers.device import rows as device_rows

from .builtin import write_builtin

# Report order; ids not listed follow alphabetically.
ORDER = ("coverage", "stability", "a11y", "perf", "adaptive", "platform", "store", "security", "stack")
PROFILES: dict[str, tuple[str, ...] | None] = {
    "full": None,
    "release": ("store", "platform", "security", "adaptive"),
    "a11y": ("a11y",),
}
SEVERITIES = ("error", "warning", "info")
STATUS_WORDS = {
    "pass": "Passing",
    "warn": "Needs attention",
    "fail": "Failing",
    "info": "Info",
    "not_run": "Not run",
}
NOT_AUDITS = ("index.json",)  # files in audits/ that aren't one audit
TOP = 10
DISMISSED = ("wontfix", "false_positive")
CRAWL_ONLY = ("coverage",)  # about how the crawl went, not the app: kept out of top findings and the fix list


def _read(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def load_audits(run: Path, data: dict | None = None, write: bool = True) -> dict[str, dict]:
    """Every audit of the run: the built-in four, refreshed (and written when `write`), plus each tool's file."""
    run = Path(run)
    if write:
        audits = write_builtin(run, data)
    else:
        from .builtin import build_builtin

        audits = build_builtin(run, data)
    for p in sorted((run / "audits").glob("*.json")) if (run / "audits").is_dir() else []:
        if p.name in NOT_AUDITS or p.stem.endswith("-evidence") or p.stem in audits:
            continue
        a = _read(p)
        if isinstance(a, dict) and a.get("schema") == 1 and isinstance(a.get("findings"), list):
            audits[a.get("audit") or p.stem] = a
    return audits


def select(audits: dict[str, dict], only: list[str] | None = None, profile: str = "full") -> list[str]:
    wanted = only or PROFILES.get(profile)
    ids = [a for a in audits if wanted is None or a in wanted]
    rank = {a: i for i, a in enumerate(ORDER)}
    return sorted(ids, key=lambda a: (rank.get(a, len(ORDER)), a))


def _titles(run: Path, data: dict) -> dict[str, str]:
    """Display titles: the canvas's titles.json (English for a run in another language) over map.json's own."""
    out = {s["id"]: s.get("title") or s["id"] for s in data["screens"]}
    doc = _read(run / "titles.json") or {}
    out.update({k: v for k, v in (doc.get("titles") or {}).items() if k in out and v})
    return out


def _screen_ref(run: Path, s: dict, titles: dict) -> dict:
    img = s.get("thumb") or s.get("screenshot")
    return {
        "id": s["id"],
        "title": titles.get(s["id"], s["id"]),
        "activity": s.get("activity"),
        "image": img if img and (run / img).is_file() else None,
    }


def _finding(f: dict, screens: dict, audit: dict) -> dict:
    ids = f.get("screens") or ([f["screen"]] if f.get("screen") else [])
    return {
        **f,
        "audit": audit["audit"],
        "audit_title": audit.get("title") or audit["audit"],
        "platform": f.get("platform"),
        "where": [screens[i] for i in ids if i in screens],
    }


def _counts(findings: list[dict]) -> dict[str, int]:
    return {s: sum(f.get("severity") == s for f in findings) for s in SEVERITIES}


def when(iso: str | None) -> str | None:
    """'2026-10-15T19:17:00+00:00' → '2026-10-15 19:17 UTC', for people."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return iso


FOLD_AT = 3  # this many findings of one kind in one category read better as one row


def fold(fs: list[dict], category: str) -> list[dict]:
    """Rows for a category: findings of one kind (same id prefix, e.g. every `untried::*`) become one row with
    the shared detail and fix, each finding's title, and every screen."""
    kinds: dict[str, list[dict]] = {}
    for f in fs:
        kinds.setdefault(f["id"].split("::")[0], []).append(f)
    rows, folded = [], set()
    for f in fs:
        kind = f["id"].split("::")[0]
        items = kinds[kind]
        if len(items) < FOLD_AT:
            rows.append(f)
            continue
        if kind in folded:
            continue
        folded.add(kind)

        def shared(key, items=items):
            v = items[0].get(key)
            return v if all(i.get(key) == v for i in items) else None

        where, seen = [], set()
        for i in items:
            for w in i.get("where") or []:
                if w["id"] not in seen:
                    seen.add(w["id"])
                    where.append(w)
        rows.append(
            {
                "fold": True,
                "id": f"{kind}::*",
                "audit": f["audit"],
                "audit_title": f["audit_title"],
                "severity": min((i["severity"] for i in items), key=SEVERITIES.index),
                "title": f"{category}: {len(items)} findings",
                "items": [i["title"] for i in items],
                "detail": shared("detail"),
                "fix": shared("fix"),
                "refs": shared("refs"),
                "platform": shared("platform"),
                "where": where,
            }
        )
    return rows


def _due_key(f: dict) -> tuple:
    return (SEVERITIES.index(f.get("severity", "info")), f.get("due") or "9999", -len(f.get("where") or []))


def build_document(
    run: str | Path, only: list[str] | None = None, profile: str = "full", write_audits: bool = True
) -> dict:
    run = Path(run)
    data = load_map(run)
    audits = load_audits(run, data, write=write_audits)
    titles = _titles(run, data)
    screens = {s["id"]: _screen_ref(run, s, titles) for s in data["screens"]}
    r = data["run"]
    app, dev = r.get("app") or {}, r.get("device") or {}

    sections = []
    for aid in select(audits, only, profile):
        a = audits[aid]
        if a.get("source") == "sample":  # placeholder data never goes in a report
            continue
        findings = [_finding(f, screens, a) for f in a.get("findings") or [] if not f.get("sample")]
        findings.sort(key=_due_key)
        groups: dict[str, list[dict]] = {}
        for f in findings:
            groups.setdefault(f.get("category") or "Other", []).append(f)
        groups = {cat: fold(fs, cat) for cat, fs in groups.items()}
        sections.append(
            {
                "id": aid,
                "title": a.get("title") or aid,
                "status": a.get("status") or "info",
                "status_word": a.get("status_label") or STATUS_WORDS.get(a.get("status") or "info", "Info"),
                "score": a.get("score"),
                "score_note": a.get("score_note"),
                "summary": a.get("summary") or "",
                "tool": a.get("tool"),
                "generated_at": a.get("generated_at"),
                "source": a.get("source") or "run",
                "metrics": [m for m in a.get("metrics") or [] if not m.get("sample")],
                "charts": [c for c in a.get("charts") or [] if not c.get("sample") and c.get("data")],
                "findings": findings,
                "groups": groups,
                "counts": _counts(findings),
                "manual": a.get("manual") or [],
                "refs": a.get("refs") or [],
            }
        )

    every = [f for s in sections for f in s["findings"]]
    top = sorted(
        (
            f
            for f in every
            if f.get("severity") != "info"
            and f["audit"] not in CRAWL_ONLY
            and f.get("triage") not in DISMISSED
        ),
        key=_due_key,
    )[:TOP]
    deadlines = sorted((f for f in every if f.get("due")), key=lambda f: f["due"])
    sources: dict[str, dict] = {}
    for s in sections:
        for ref in s["refs"] + [x for f in s["findings"] for x in f.get("refs") or []]:
            if ref.get("url"):
                sources.setdefault(ref["url"], ref)

    return {
        "schema": 1,
        "title": f"{app.get('label') or app.get('package') or r.get('id')} · App report",
        "generated_at": when(datetime.now(UTC).isoformat(timespec="seconds")),
        "tool": f"appscreenmap {__version__}",
        "profile": "custom" if only else profile,
        "run_dir": str(run),
        "cover": {
            "app": app.get("label") or app.get("package"),
            "package": app.get("package"),
            "version": app.get("version"),
            "platform": dev.get("platform") or "android",
            "canvas": r.get("id"),
            "crawled": when(r.get("finished_at") or r.get("updated_at") or r.get("started_at")),
            "screens": sum(s["kind"] == "app" for s in data["screens"]),
        },
        "summary": [
            {k: s[k] for k in ("id", "title", "status", "status_word", "score", "summary", "counts")}
            for s in sections
        ],
        "top": top,
        "deadlines": deadlines,
        "conditions": {
            "device": describe(dev) if dev else None,
            "rows": [(k, v) for k, v in device_rows(dev) if v] if dev else [],
            "scenarios": [
                {
                    "id": sc.get("id"),
                    "label": sc.get("label"),
                    "run": sc.get("run_id"),
                    "screens": len(sc.get("screens") or []),
                }
                for sc in r.get("scenarios") or []
            ],
        },
        "sections": sections,
        "appendix": {
            "method": [
                "Screens, transitions and evidence come from crawling the app on the device above; each audit names the tool that produced it.",
                "Scores are 0–100, higher is better; each audit says how it scores. A null score means the audit doesn't score.",
                "Automated checks find likely problems, not proof of conformance. Manual checks are listed as not tested until someone runs them.",
                "Findings marked won't fix or false positive in triage stay in the report with their triage state.",
            ],
            "sources": list(sources.values()),
            "glossary": [
                ("Canvas", "The app's one map: every crawl and screen filed by hand, merged as scenarios."),
                (
                    "Finding",
                    "One problem an audit found, with severity, where, the fix and its official source.",
                ),
                ("Severity", "error: must fix; warning: should fix; info: worth knowing."),
                (
                    "Requirement",
                    "A store or platform rule's state: met, due, blocked, upcoming or not checked.",
                ),
            ],
        },
    }


FORMATS = ("md", "html", "fixes")  # pdf and docx come next (docs/PLAN.md §8.7, stage 2)


def write_report(
    run: str | Path,
    formats: list[str],
    only: list[str] | None = None,
    profile: str = "full",
    out: str | Path | None = None,
) -> dict[str, Path]:
    """Build the model once and write each format into `<run>/reports/` (or `out`)."""
    from . import fixes, htmldoc, markdown

    renderers = {"md": markdown.render, "html": htmldoc.render, "fixes": fixes.render}
    doc = build_document(run, only, profile)
    out_dir = Path(out) if out else Path(run) / "reports"
    return {f: renderers[f](doc, out_dir) for f in formats}
