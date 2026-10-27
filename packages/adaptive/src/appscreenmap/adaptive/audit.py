"""The adaptive UI audit from a build's static facts → `audits/adaptive.json` (docs/MAP_SCHEMA.md audit shape).

Size checks (`detect: condition`) need a crawl per device profile and are reported as not run until one exists;
`detect: manual` rules are listed as not tested, with their steps.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from .facts import LOCKED, NOSENSOR, SIZE_CHANGES

RULES = Path(__file__).with_name("rules.json")
SCORE_NOTE = "100 minus 20 per error, 8 per warning"
STATUS_LABEL = {"fail": "Not adaptive", "warn": "Needs work on large screens", "pass": "No static issues"}


def load_rules() -> dict:
    return json.loads(RULES.read_text())


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _short(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _finding(cat: dict, rule_id: str, items: list[str], detail: str | None = None, **extra) -> dict:
    r = next(x for x in cat["rules"] if x["id"] == rule_id)
    f = {
        "id": f"adaptive::{rule_id}",
        "severity": extra.pop("severity", r["severity"]),
        "title": r["title"] + (f" ({len(items)} activities)" if len(items) > 1 else ""),
        "detail": detail or r["why"],
        "fix": r["fix"],
        "platform": r["platform"],
        "category": {
            "ready": "Tier 3 · adaptive ready",
            "optimized": "Tier 2 · adaptive optimized",
            "differentiated": "Tier 1 · adaptive differentiated",
            "hig": "Apple HIG",
        }[r["tier"]],
        "tier": r["tier"],
        "refs": [cat["sources"][k] for k in r["refs"]],
        **extra,
    }
    if r.get("official_id"):
        f["official_id"] = r["official_id"]
    if items:
        f["items"] = items
    return f


def android_findings(facts: dict, cat: dict, today: date) -> list[dict]:
    a17 = cat["android17"]
    target = facts.get("target_sdk")
    # Android 16 ignores these limits on large screens (sw >= 600 dp) for apps targeting API 36, with a temporary
    # opt-out; API 37 (Android 17) removes the opt-out. Games are exempt (android:appCategory).
    if facts.get("game"):
        when = {"severity": "info", "requirement": "exempt (game)"}
    elif (
        target is not None
        and target >= a17["target_api"]
        or target is not None
        and target >= a17["target_api"] - 1
        and not facts.get("opt_out")
    ):
        when = {"requirement": "ignored on large screens"}
    elif today.isoformat() < a17["play_date"]:
        when = {"requirement": "due", "due": a17["play_date"]}
    else:
        when = {"requirement": "blocked", "severity": "error"}
    acts = [a for a in facts.get("activities") or [] if not a.get("alias")]
    out = []
    locked = [f"{_short(a['name'])} → {LOCKED[a['orientation']]}" for a in acts if a["orientation"] in LOCKED]
    if locked:
        out.append(_finding(cat, "orientation-locked", locked, **dict(when)))
    nosensor = [_short(a["name"]) for a in acts if a["orientation"] == NOSENSOR]
    if nosensor:
        out.append(_finding(cat, "orientation-nosensor", nosensor))
    fixed = [_short(a["name"]) for a in acts if a["resizeable"] is False]
    if fixed:
        out.append(_finding(cat, "resize-disabled", fixed, **dict(when)))
    ratio = [
        f"{_short(a['name'])}: "
        + ", ".join(f"{k} {a[k2]}" for k, k2 in (("min", "min_aspect"), ("max", "max_aspect")) if a.get(k2))
        for a in acts
        if a.get("min_aspect") or a.get("max_aspect")
    ]
    if ratio:
        out.append(_finding(cat, "aspect-ratio-limited", ratio, **dict(when)))
    recreated = [_short(a["name"]) for a in acts if (a["config_changes"] & SIZE_CHANGES) != SIZE_CHANGES]
    if recreated:
        out.append(_finding(cat, "recreated-on-resize", recreated))
    return out


def ios_findings(facts: dict, cat: dict) -> list[dict]:
    out = []
    if facts.get("requires_fullscreen"):
        out.append(_finding(cat, "ios-requires-fullscreen", []))
    if not facts.get("scenes"):
        out.append(_finding(cat, "ios-no-scenes", []))
    fam = facts.get("device_family") or []
    if fam and 2 not in fam:
        out.append(_finding(cat, "ios-iphone-only", []))
    o = facts.get("orientations") or []
    ipad = facts.get("orientations_ipad") or []  # a universal app may rotate on iPad only
    if o and all("Portrait" in x for x in o) and all("Portrait" in x for x in ipad):
        out.append(_finding(cat, "ios-portrait-only", []))
    if facts.get("xcode_major") is not None and facts["xcode_major"] <= 26:
        out.append(
            _finding(
                cat,
                "ios-built-before-duo",
                [],
                detail=f"Built with Xcode {facts['xcode_major']}. "
                + next(r["why"] for r in cat["rules"] if r["id"] == "ios-built-before-duo"),
            )
        )
    return out


def build_audit(facts: dict, today: date | None = None) -> dict:
    today = today or datetime.now(UTC).date()
    cat = load_rules()
    ios = facts.get("platform") == "ios"
    plat = "ios" if ios else "android"
    readable = "activities" in facts or "scenes" in facts
    findings = (ios_findings(facts, cat) if ios else android_findings(facts, cat, today)) if readable else []
    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["id"]))
    n = {s: sum(f["severity"] == s for f in findings) for s in order}
    rules = [r for r in cat["rules"] if r["platform"] in (plat, "any")]
    size_rules = [r for r in rules if r["detect"] == "condition"]
    status = "not_run" if not readable else "fail" if n["error"] else "warn" if n["warning"] else "pass"
    notes = facts.get("notes") or []
    summary = (
        "; ".join(notes) or "Nothing could be read."
        if not readable
        else f"{_plural(n['error'], 'error')} and {_plural(n['warning'], 'warning')} from the "
        + ("Info.plist" if ios else "manifest")
        + f"; {_plural(len(size_rules), 'size check')} need a crawl on a foldable or tablet profile."
    )
    metrics = (
        [
            {
                "label": "build",
                "value": f"Xcode {facts['xcode_major']}" if facts.get("xcode_major") else "unknown",
            }
        ]
        if ios
        else [
            {"label": "targetSdk", "value": facts.get("target_sdk") or "unknown"},
            {"label": "activities", "value": len(facts.get("activities") or [])},
        ]
    )
    metrics += [
        {"label": "static rules", "value": sum(r["detect"] == "static" for r in rules)},
        {
            "label": "size checks",
            "value": "not run",
            "hint": "needs a crawl per device profile: " + "; ".join(r["title"] for r in size_rules),
            "tone": "info",
        },
        {"label": "rules checked", "value": cat["checked"], "hint": "rules.json"},
    ]
    return {
        "schema": 1,
        "audit": "adaptive",
        "title": "Adaptive UI",
        "tool": "appscreenmap adaptive (" + ("Info.plist" if ios else "aapt2") + ")",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "run",
        "status": status,
        **({"status_label": STATUS_LABEL[status]} if status in STATUS_LABEL else {}),
        "score": max(0, 100 - 20 * n["error"] - 8 * n["warning"]) if readable else None,
        "score_note": SCORE_NOTE,
        "summary": summary,
        "metrics": metrics,
        "charts": [],
        "findings": findings,
        "manual": [
            {"id": r["id"], "title": r["title"], "steps": r["steps"], "tier": r["tier"]}
            for r in rules
            if r["detect"] == "manual"
        ],
        "refs": [
            cat["sources"][k] for k in (("duo", "hig-layout") if ios else ("quality", "android17", "adapt"))
        ],
    }


def write_audit(run: Path, audit: dict) -> Path:
    d = Path(run) / "audits"
    d.mkdir(exist_ok=True)
    p = d / "adaptive.json"
    p.write_text(json.dumps(audit, indent=1) + "\n")
    return p
