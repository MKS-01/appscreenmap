"""The audit: every source's evidence in, `audits/security.json` out, worded and scored from the rule catalogue."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .rules import load_rules

CATEGORY_LABEL = {
    "manifest": "Manifest",
    "static": "Static scan",
    "dynamic": "Dynamic run",
    "data": "Data on device",
}
SCORE_NOTE = "100 minus 20 per error, 8 per warning, 2 per info"


def build_audit(sources: dict[str, dict], platform: str = "android") -> dict:
    """Combine the evidence of every source that has run into one `audits/security.json` document."""
    rules = {r.id: r for r in load_rules()}
    ran = sorted({c for s in sources.values() for c in s.get("ran", [])})
    notes = [n for s in sources.values() for n in s.get("notes", [])]
    findings = []
    for ev in sources.values():
        for f in ev.get("findings", []):
            r = rules[f["rule"]]
            key = f.get("key")
            title = f"{r.title}: {f['subject']}" if f.get("subject") else r.title
            findings.append(
                {
                    "id": f"{r.id}:{key}" if key else r.id,
                    "severity": f.get("severity") or r.severity,
                    "title": title,
                    "detail": f"{f['detail']} {r.why}",
                    "fix": r.fix,
                    "platform": platform,
                    "category": CATEGORY_LABEL[r.category],
                    "refs": [{"title": x.title, "url": x.url, "publisher": x.publisher} for x in r.refs],
                }
            )
    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["id"]))
    n = {s: sum(1 for f in findings if f["severity"] == s) for s in order}
    score = max(0, 100 - 20 * n["error"] - 8 * n["warning"] - 2 * n["info"])
    status = (
        "fail" if n["error"] else "warn" if n["warning"] else "info"
    )  # never "pass": some rules aren't checked yet
    not_checked = [r.id for r in rules.values() if r.status == "planned" and r.platform in (platform, "both")]
    skipped = [c for c in ("manifest", "static", "data", "dynamic") if c not in ran]
    parts = [f"{n['error']} error(s), {n['warning']} warning(s), {n['info']} info"]
    parts.append("checked: " + (", ".join(ran) or "nothing"))
    if skipped:
        parts.append("not run: " + ", ".join(skipped))
    return {
        "schema": 1,
        "audit": "security",
        "title": "Security",
        "tool": "appscreenmap security (aapt2, built-in scans"
        + (", Frida log)" if "dynamic" in ran else ")"),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "run",
        "status": status,
        "score": score,
        "score_note": SCORE_NOTE,
        "summary": " · ".join(parts),
        "metrics": [
            {"label": "checks run", "value": ", ".join(ran) or "none"},
            {
                "label": "not run",
                "value": ", ".join(skipped) or "none",
                "tone": "warn" if skipped else "good",
            },
            {
                "label": "rules not checked yet",
                "value": len(not_checked),
                "tone": "info",
                "hint": ", ".join(not_checked),
            },
            *({"label": "note", "value": t, "tone": "warn"} for t in notes),
        ],
        "charts": [],
        "findings": findings,
        "refs": [],
    }


def load_evidence(run: Path) -> dict[str, dict]:
    p = run / "audits" / "security-evidence.json"
    try:
        return json.loads(p.read_text()).get("sources", {})
    except (OSError, ValueError):
        return {}


def write_audit(run: Path, sources: dict[str, dict], platform: str = "android") -> dict:
    """Store the evidence ledger and the audit built from it in the run folder."""
    d = run / "audits"
    d.mkdir(exist_ok=True)
    (d / "security-evidence.json").write_text(json.dumps({"schema": 1, "sources": sources}, indent=1) + "\n")
    audit = build_audit(sources, platform)
    (d / "security.json").write_text(json.dumps(audit, indent=1) + "\n")
    return audit
