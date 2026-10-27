"""The report as work: `fixes.md`, one task per distinct problem, for the developer or a coding agent fixing the app.

`fixes.json` beside it remembers every task, so a task whose finding is gone after a re-crawl is ticked with the run
that showed it gone, instead of disappearing. Plain Markdown with no HTML, so it pastes into an issue or a PR.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .document import CRAWL_ONLY, DISMISSED
from .markdown import SEV, link

FIXABLE = ("error", "warning")
# How to check a fix, per audit; a finding's own `verify` wins.
VERIFY = {
    "a11y": "Re-crawl the screens listed, then `appscreenmap a11y <canvas>`; this rule should report no issue there.",
    "perf": "Re-crawl, then `appscreenmap perf <canvas>`; the screen should load under budget with little jank.",
    "stability": "Re-crawl the scenario; the crawl should finish with no crash event.",
    "store": "Rebuild, then `appscreenmap store`; the requirement should read met.",
    "security": "Rebuild, then `appscreenmap security`; the finding should be gone.",
    "stack": "Rebuild and install, then `appscreenmap stack --package <pkg>`.",
}


def _key(audit: str, fid: str) -> str:
    return fid if fid.startswith(f"{audit}::") else f"{audit}::{fid}"


def _strip_screen(fid: str) -> str:
    return "::".join(p for p in fid.split("::") if not re.fullmatch(r"s\d+", p))


def dismissed_from(doc: dict) -> dict[str, str]:
    """Task ids triaged away (won't fix / false positive) → their triage: never counted as fixed."""
    return {
        _key(s["id"], f["id"]): f["triage"]
        for s in doc["sections"]
        if s["id"] not in CRAWL_ONLY
        for f in s["findings"]
        if f.get("severity") in FIXABLE and f.get("triage") in DISMISSED
    }


def tasks_from(doc: dict) -> list[dict]:
    """Open tasks: errors and warnings from app audits, not dismissed in triage. The same finding on several
    screens (same id apart from the screen, same title) is one task listing every screen."""
    grouped: dict[tuple, dict] = {}
    for s in doc["sections"]:
        if s["id"] in CRAWL_ONLY:
            continue
        for f in s["findings"]:
            if f.get("severity") not in FIXABLE or f.get("triage") in DISMISSED:
                continue
            g = (s["id"], _strip_screen(f["id"]), f["title"])
            if g in grouped:
                seen = {w["id"] for w in grouped[g]["where"]}
                grouped[g]["where"] += [w for w in f.get("where") or [] if w["id"] not in seen]
                continue
            grouped[g] = {**f, "where": list(f.get("where") or []), "task": _key(s["id"], f["id"])}
    order = lambda t: (FIXABLE.index(t["severity"]), t.get("due") or "9999", -len(t["where"]))
    return sorted(grouped.values(), key=order)


def _verified_on(doc: dict) -> str:
    """The run a fix was seen in: the canvas's latest scenario run, else the canvas itself."""
    sc = doc["conditions"]["scenarios"]
    return (sc[-1]["run"] if sc and sc[-1].get("run") else None) or doc["cover"]["canvas"]


def render(doc: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_file = out_dir / "fixes.json"
    try:
        state = json.loads(state_file.read_text())
    except (OSError, ValueError):
        state = {"schema": 1, "tasks": {}}
    known = state.setdefault("tasks", {})
    today = datetime.now(UTC).date().isoformat()
    checked = {s["id"] for s in doc["sections"] if s["status"] != "not_run"}

    open_ = tasks_from(doc)
    open_ids = {t["task"] for t in open_}
    for t in open_:
        prev = known.get(t["task"]) or {}
        known[t["task"]] = {
            "title": t["title"],
            "audit": t["audit"],
            "severity": t["severity"],
            "first_seen": prev.get("first_seen") or today,
        }
    dismissed = dismissed_from(doc)
    # Gone from an audit that ran again: fixed. Triaged away: dismissed, not fixed. Its audit didn't run: unchanged.
    for tid, t in known.items():
        if tid in open_ids:
            continue
        if tid in dismissed:
            t.pop("fixed_on", None), t.pop("verified_in", None)
            t["dismissed"] = dismissed[tid]
        elif t["audit"] in checked and not t.get("fixed_on"):
            t.pop("dismissed", None)
            t["fixed_on"] = today
            t["verified_in"] = _verified_on(doc)
    done = [(tid, t) for tid, t in known.items() if t.get("fixed_on") and tid not in open_ids]
    stale = [
        (tid, t)
        for tid, t in known.items()
        if tid not in open_ids
        and not t.get("fixed_on")
        and not t.get("dismissed")
        and t["audit"] not in checked
    ]

    c = doc["cover"]
    L = [
        f"# Fixes · {c['app']}",
        "",
        (
            f"From the `{doc['profile']}` report of canvas `{c['canvas']}`, {doc['generated_at']}. "
            f"{len(open_)} open, {len(done)} fixed. Ordered by severity, then deadline, then how many screens it touches."
        ),
        "",
        (
            "Work top-down. Each task says where, what was seen, the fix, its official source and how to check it. "
            "After fixing, re-crawl and run `appscreenmap report <canvas> --format fixes`; tasks whose finding is gone are ticked."
        ),
        "",
    ]
    for i, t in enumerate(open_, 1):
        L.append(f"- [ ] **{i}. {t['title']}**")
        meta = [f"`{t['task']}`", SEV[t["severity"]], t["audit_title"]]
        if t.get("category"):
            meta.append(t["category"])
        if t.get("platform"):
            meta.append(t["platform"])
        if t.get("due"):
            meta.append(f"due {t['due']}")
        if t.get("triage") == "confirmed":
            meta.append("confirmed in triage")
        L.append("  " + " · ".join(meta))
        if t["where"]:
            wh = "; ".join(
                f"{w['id']} {w['title']}"
                + (f" (`{w['activity'].rsplit('.', 1)[-1]}`)" if w.get("activity") else "")
                + (f", `{w['image']}`" if w.get("image") else "")
                for w in t["where"]
            )
            L.append(f"  - **Where:** {wh}")
        if t.get("elements"):
            els = ", ".join(
                f"{x['screen']} `{x['rid'].rsplit('/', 1)[-1]}`"
                if x.get("rid")
                else f"{x['screen']} “{x.get('label')}”"
                for x in t["elements"]
            )
            L.append(f"  - **Elements:** {els}")
        if t.get("detail"):
            L.append(f"  - **Seen:** {t['detail']}")
        if t.get("fix"):
            L.append(f"  - **Fix:** {t['fix']}")
        if t.get("refs"):
            L.append("  - **Source:** " + " · ".join(link(r) for r in t["refs"]))
        L.append(
            f"  - **Check it's fixed:** {t.get('verify') or VERIFY.get(t['audit'], 'Re-run the audit that wrote `audits/' + t['audit'] + '.json`; the finding should be gone.')}"
        )
        L.append("")
    if not open_:
        L += ["No open errors or warnings.", ""]

    manual = [(s["title"], m) for s in doc["sections"] if s["id"] not in CRAWL_ONLY for m in s["manual"]]
    if manual:
        L += ["## Verify by hand", ""]
        L += [
            f"- [ ] {title}: **{m.get('title')}**. {m.get('steps') or m.get('detail') or ''}".rstrip()
            for title, m in manual
        ]
        L.append("")
    if stale:
        L += [
            "## Not re-checked",
            "",
            "Open last time; their audit wasn't in this report, so they're unconfirmed.",
            "",
        ]
        L += [f"- [ ] {t['title']} · `{tid}` · since {t['first_seen']}" for tid, t in stale]
        L.append("")
    if done:
        L += ["## Fixed", ""]
        L += [
            f"- [x] {t['title']} · `{tid}` · gone in `{t['verified_in']}` on {t['fixed_on']}"
            for tid, t in done
        ]
        L.append("")

    state_file.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")
    p = out_dir / "fixes.md"
    p.write_text("\n".join(L))
    return p
