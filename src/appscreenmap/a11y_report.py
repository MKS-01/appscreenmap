"""Accessibility report for a run: WCAG 2.2 status per criterion, findings with evidence, coverage.

Inputs: `a11y.json` (crawler checks, rebuilt here), `notes.json` (triage, plus viewer findings the
user confirmed in the web viewer), `map.json` (screens, screenshots).
Outputs: `a11y-report.html` (self-contained, shareable) and `a11y-report.md` (+ `a11y/crops/*.jpg`).
"""

from __future__ import annotations

import base64
import html
import io
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw

from . import __version__
from .a11y import RULES, audit_run
from .model import load_map
from .wcag import BY_SC, DEVICE_TESTS, LEVEL_ORDER, VIEWER_RULES, criteria_up_to, sc_key

MAX_EVIDENCE = 8  # screenshot crops per criterion
STATUS = {
    "fail": ("Fails", "Confirmed failure (triaged in the viewer or notes.json)."),
    "issues": ("Issues found", "Automated checks found likely failures that a person hasn't confirmed yet."),
    "review": ("Needs review", "Flagged for a person to check; not a failure on its own."),
    "pass_auto": ("No issues detected", "Automated checks ran and found nothing. Not proof of conformance."),
    "viewer": ("Check in viewer", "Covered by the viewer's per-screen checks; none confirmed yet."),
    "not_tested": ("Not tested", "Needs a device or manual test (see the a11y-audit skill)."),
}


# ── model ────────────────────────────────────────────────────────────────────


def _viewer_findings(notes: dict, screens: dict) -> list[dict]:
    """Viewer issues the user marked 'confirmed' (their key encodes screen, rule, label, position)."""
    out = []
    for key, t in (notes.get("a11y") or {}).items():
        if t.get("status") != "confirmed":
            continue
        parts = key.split("::")
        if len(parts) < 5 or parts[1] not in VIEWER_RULES:
            continue
        screen, rule, ident, pos = parts[0], parts[1], parts[2], parts[-1]
        label = "::".join(parts[3:-1])
        x, _, y = pos.partition(",")
        meta = VIEWER_RULES[rule]
        out.append(
            {
                "key": key,
                "screen": screen,
                "rule": rule,
                "sc": meta["sc"],
                "severity": meta["severity"],
                "level": BY_SC[meta["sc"]].level if meta["sc"] else None,
                "kind": "viewer",
                "label": label,
                "detail": meta["title"] + (f" ({t['note']})" if t.get("note") else ""),
                "point": [int(x), int(y)] if x.lstrip("-").isdigit() and y.lstrip("-").isdigit() else None,
                "bounds": None,
                "rid": ident if "/" in ident else "",
                "triage": "confirmed",
                "source": "viewer",
                "screen_title": screens.get(screen, {}).get("title", screen),
            }
        )
    return out


def _group(fs: list[dict]) -> list[dict]:
    """One entry per distinct element: the same control flagged on many screens (a bottom nav item,
    a toolbar icon) is one finding that appears on several screens."""
    groups: dict[tuple, dict] = {}
    for f in sorted(fs, key=lambda f: (f["screen"], f["label"])):
        b = f.get("bounds") or ([*f["point"], 0, 0] if f.get("point") else [0, 0, 0, 0])
        key = (f["rule"], f["label"], f.get("rid") or f.get("class") or "", *(v // 40 for v in b))
        if key in groups:
            g = groups[key]
            if f["screen"] not in g["screens"]:
                g["screens"].append(f["screen"])
            g["instances"] += 1
            if f["triage"] == "confirmed":
                g["triage"] = "confirmed"
        else:
            groups[key] = {**f, "screens": [f["screen"]], "instances": 1}
    return sorted(groups.values(), key=lambda g: (-len(g["screens"]), g["screens"][0], g["label"]))


def _not_run_reason(sc: str, run: dict) -> str | None:
    """Why the crawler's check for this criterion couldn't say anything for this run."""
    if sc == "1.3.4" and "orientation_locked" not in run.get("app", {}):
        return "manifest not read for this run"
    if sc == "1.4.4" and (run.get("device", {}).get("font_scale") or 1.0) < 2.0:
        return "needs a --font-scale 2.0 crawl"
    return None


def build_model(run_dir: str | Path, level: str = "AA") -> dict:
    run_dir = Path(run_dir)
    data = load_map(run_dir)
    audit = audit_run(run_dir)  # refresh a11y.json with current triage
    notes = {}
    if (run_dir / "notes.json").is_file():
        try:
            notes = json.loads((run_dir / "notes.json").read_text())
        except (ValueError, OSError):
            notes = {}
    screens = {s["id"]: s for s in data["screens"]}
    crawler = [
        {**i, "source": "crawler", "screen_title": screens.get(i["screen"], {}).get("title", i["screen"])}
        for i in audit["issues"]
        if i["triage"] not in ("false_positive",)
    ]
    findings = crawler + _viewer_findings(notes, screens)
    wontfix = [f for f in findings if f["triage"] == "wontfix"]
    active = [f for f in findings if f["triage"] != "wontfix"]

    by_sc: dict[str, list[dict]] = defaultdict(list)
    best_practice: list[dict] = []
    for f in active:
        if f["sc"] is None:
            best_practice.append(f)
        elif LEVEL_ORDER[BY_SC[f["sc"]].level] <= LEVEL_ORDER[level]:
            by_sc[f["sc"]].append(f)

    crawler_scs = {r.sc for r in RULES.values()}
    viewer_scs = {m["sc"] for m in VIEWER_RULES.values() if m["sc"]}
    rows = []
    for c in criteria_up_to(level):
        fs = by_sc.get(c.sc, [])
        if any(f["triage"] == "confirmed" for f in fs):
            status = "fail"
        elif any(f["kind"] == "automated" and f["severity"] in ("error", "warning") for f in fs):
            status = "issues"
        elif fs:
            status = "review"
        elif c.sc in crawler_scs and not _not_run_reason(c.sc, data["run"]):
            status = "pass_auto"
        elif c.sc in viewer_scs:
            status = "viewer"
        else:
            status = "not_tested"
        how = []
        if c.sc in crawler_scs:
            how.append("crawler")
        if c.sc in viewer_scs:
            how.append("viewer")
        if c.sc in DEVICE_TESTS:
            how.append("device")
        rows.append(
            {
                "sc": c.sc,
                "name": c.name,
                "level": c.level,
                "principle": c.principle,
                "url": c.url,
                "new": c.new_in_22,
                "advisory": c.native_advisory,
                "status": status,
                "how": how or ["manual"],
                "count": len(fs),
                "note": _not_run_reason(c.sc, data["run"]) if not fs else None,
            }
        )

    app_screens = [s for s in data["screens"] if s["kind"] == "app"]
    per_screen = Counter(f["screen"] for f in active)
    run = data["run"]
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "tool": f"appscreenmap {__version__}",
        "level": level,
        "run": run,
        "audit": {k: audit[k] for k in ("dp_scale", "density_exact", "font_scale")},
        "rows": rows,
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "findings_by_sc": {sc: _group(v) for sc, v in by_sc.items()},
        "best_practice": best_practice,
        "wontfix": wontfix,
        "severity_counts": dict(Counter(f["severity"] for fs in by_sc.values() for f in fs)),
        "screens": [
            {
                "id": s["id"],
                "title": s["title"],
                "thumb": s.get("thumb"),
                "screenshot": s.get("screenshot"),
                "width": s.get("width"),
                "height": s.get("height"),
                "issues": per_screen.get(s["id"], 0),
            }
            for s in app_screens
        ],
        "triaged": sum(1 for f in findings if f["triage"] != "open"),
        "viewer_imported": sum(1 for f in findings if f["source"] == "viewer"),
    }


# ── evidence images ──────────────────────────────────────────────────────────


def _crop(run_dir: Path, screen: dict | None, f: dict, width: int = 300) -> bytes | None:
    """A crop of the screenshot around the finding, with the element outlined."""
    if not screen or not screen.get("screenshot") or not (run_dir / screen["screenshot"]).is_file():
        return None
    with Image.open(run_dir / screen["screenshot"]) as im:
        im = im.convert("RGB")
        W, H = im.size
        if f.get("bounds") and any(f["bounds"]):
            x1, y1, x2, y2 = f["bounds"]
        elif f.get("point"):
            x, y = f["point"]
            x1, y1, x2, y2 = x, y, x + 60, y + 60
        else:
            return None
        pad_x, pad_y = max(120, (x2 - x1) // 2), max(120, (y2 - y1) // 2)
        box = (max(0, x1 - pad_x), max(0, y1 - pad_y), min(W, x2 + pad_x), min(H, y2 + pad_y))
        draw = ImageDraw.Draw(im)
        for i in range(6):
            draw.rectangle([x1 - i, y1 - i, x2 + i, y2 + i], outline=(220, 38, 38))
        crop = im.crop(box)
        crop.thumbnail((width, width * 2))
        buf = io.BytesIO()
        crop.save(buf, "JPEG", quality=80, optimize=True)
        return buf.getvalue()


# ── HTML ─────────────────────────────────────────────────────────────────────

_CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1b1b1f;--muted:#5d5d66;--line:#e3e3e0;--accent:#3d5afe;
--fail:#b42318;--fail-bg:#fde8e7;--issues:#b54708;--issues-bg:#fef0c7;--review:#6941c6;--review-bg:#f0ebfd;
--pass:#067647;--pass-bg:#dcfae6;--viewer:#175cd3;--viewer-bg:#e0eaff;--nt:#5d5d66;--nt-bg:#efefed}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1d1d21;--ink:#ececf1;--muted:#a2a2ad;--line:#2e2e34;
--fail-bg:#3b1715;--issues-bg:#3a2a10;--review-bg:#2a2140;--pass-bg:#113322;--viewer-bg:#162544;--nt-bg:#26262b;
--fail:#ff8a80;--issues:#fdb022;--review:#b9a2f5;--pass:#6ce9a6;--viewer:#84adff;--nt:#a2a2ad}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:32px 20px 64px}
a{color:var(--accent)}h1{font-size:28px;margin:0 0 4px}h2{font-size:20px;margin:40px 0 12px}
h3{font-size:16px;margin:0}.muted{color:var(--muted)}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px 24px;margin:16px 0;
padding:16px;background:var(--card);border:1px solid var(--line);border-radius:12px;font-size:14px}
.meta b{display:block;font-size:12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.card .n{font-size:30px;font-weight:700;line-height:1.1}.card .l{font-size:13px;color:var(--muted)}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.s-fail{color:var(--fail);background:var(--fail-bg)}.s-issues{color:var(--issues);background:var(--issues-bg)}
.s-review{color:var(--review);background:var(--review-bg)}.s-pass_auto{color:var(--pass);background:var(--pass-bg)}
.s-viewer{color:var(--viewer);background:var(--viewer-bg)}.s-not_tested{color:var(--nt);background:var(--nt-bg)}
.tag{display:inline-block;font-size:11px;font-weight:600;padding:1px 6px;border-radius:5px;border:1px solid var(--line);
color:var(--muted);margin-left:6px;vertical-align:middle}
.note{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;
padding:12px 16px;margin:16px 0;font-size:14px}
.finding{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:14px 0}
.finding header{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between}
.why{margin:8px 0 4px}.fix{margin:4px 0 12px;font-size:14px}.fix b{color:var(--pass)}
.ev{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.ev figure{margin:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--bg)}
.ev img{display:block;width:100%;height:auto}.ev figcaption{padding:8px 10px;font-size:13px}
.ev figcaption code{font-size:12px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;
overflow:hidden;font-size:14px}th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:var(--bg)}
tr.p td{background:var(--bg);font-weight:700}
.screens{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:12px}
.screens figure{margin:0;text-align:center;font-size:12px}.screens img{width:100%;border-radius:8px;border:1px solid var(--line)}
.bad{color:var(--fail);font-weight:700}ul.plain{padding-left:18px}
@media print{body{background:#fff}.finding,.card,table,.meta{break-inside:avoid}}
"""


def _where(f: dict) -> str:
    screens = f.get("screens") or [f["screen"]]
    if len(screens) == 1:
        return f"{screens[0]} · {f['screen_title']}"
    shown = ", ".join(screens[:4]) + (f" +{len(screens) - 4}" if len(screens) > 4 else "")
    return f"{len(screens)} screens: {shown}"


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _pill(status: str) -> str:
    return f'<span class="pill s-{status}">{_e(STATUS[status][0])}</span>'


def render_html(model: dict, run_dir: Path) -> str:
    run, app, dev = model["run"], model["run"].get("app", {}), model["run"].get("device", {})
    screens = {s["id"]: s for s in load_map(run_dir)["screens"]}
    sc_counts = model["status_counts"]
    total = len(model["rows"])
    title = f"Accessibility report: {app.get('label') or app.get('package')}"
    out = [
        (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{_e(title)}</title><style>{_CSS}</style></head><body><main>'
        ),
        f"<h1>{_e(title)}</h1>",
        (
            f'<div class="muted">WCAG 2.2 Level {_e(model["level"])} · generated {_e(model["generated_at"])} '
            f"by {_e(model['tool'])}</div>"
        ),
        '<div class="meta">',
        *[
            f"<div><b>{_e(k)}</b>{_e(v)}</div>"
            for k, v in [
                ("App", f"{app.get('label', '')} {app.get('version') or ''}"),
                ("Package", app.get("package")),
                ("Device", f"{dev.get('manufacturer', '')} {dev.get('model', '')}"),
                ("Android", f"{dev.get('android', '?')} (SDK {dev.get('sdk', '?')})"),
                (
                    "Screen",
                    (
                        f"{dev.get('width')}×{dev.get('height')} px, "
                        f"{dev.get('density') or '~' + str(round(model['audit']['dp_scale'] * 160))} dpi"
                    ),
                ),
                ("Font scale", dev.get("font_scale") or "1.0 (assumed)"),
                ("Run", run.get("id")),
                ("Screens audited", len(model["screens"])),
            ]
        ],
        "</div>",
        (
            '<div class="note"><b>About this report.</b> It combines automated checks from an AppScreenMap crawl '
            "with decisions recorded during review. Automated results are evidence for a person to confirm, "
            "<b>not a conformance claim</b>. Per-screen scanner checks (missing labels, contrast, field labels) run "
            f"in the web viewer; only the ones confirmed there are included ({model['viewer_imported']} imported). "
            "Criteria marked <i>Not tested</i> need device or manual testing.</div>"
        ),
        "<h2>Summary</h2>",
        '<div class="cards">',
        *[
            f'<div class="card"><div class="n">{sc_counts.get(k, 0)}</div><div class="l">{_pill(k)} of {total} criteria</div></div>'
            for k in ("fail", "issues", "review", "pass_auto", "viewer", "not_tested")
        ],
        "</div>",
        '<p class="muted">Findings by severity: '
        + ", ".join(f"{n} {s}" for s, n in sorted(model["severity_counts"].items()))
        + f". {model['triaged']} finding(s) triaged.</p>"
        if model["severity_counts"]
        else '<p class="muted">No open findings.</p>',
    ]

    # Findings
    out.append("<h2>Findings by success criterion</h2>")
    rows = {r["sc"]: r for r in model["rows"]}
    order = {"fail": 0, "issues": 1, "review": 2}
    scs = sorted(model["findings_by_sc"], key=lambda sc: (order.get(rows[sc]["status"], 9), sc_key(sc)))
    if not scs:
        out.append('<p class="muted">No findings at this level.</p>')
    for sc in scs:
        r, fs = rows[sc], model["findings_by_sc"][sc]
        rule = RULES.get(fs[0]["rule"])
        tags = ('<span class="tag">New in 2.2</span>' if r["new"] else "") + (
            '<span class="tag">Advisory for native apps</span>' if r["advisory"] else ""
        )
        out.append(
            f'<section class="finding"><header><h3>{_e(sc)} {_e(r["name"])} '
            f'<span class="muted">· Level {_e(r["level"])}</span>{tags}</h3>{_pill(r["status"])}</header>'
        )
        if rule and fs[0]["source"] == "crawler":
            out.append(f'<p class="why">{_e(rule.why)}</p><p class="fix"><b>Fix:</b> {_e(rule.fix)}</p>')
        n_inst = sum(f["instances"] for f in fs)
        out.append(
            f'<p class="muted" style="font-size:13px">{len(fs)} element(s), {n_inst} instance(s) · '
            f'<a href="{_e(r["url"])}">Understanding {_e(sc)}</a></p><div class="ev">'
        )
        for f in fs[:MAX_EVIDENCE]:
            img = _crop(run_dir, screens.get(f["screen"]), f)
            src = f'<img alt="" src="data:image/jpeg;base64,{base64.b64encode(img).decode()}">' if img else ""
            tri = ' · <span class="bad">confirmed</span>' if f["triage"] == "confirmed" else ""
            out.append(
                f"<figure>{src}<figcaption><b>{_e(f['label'])}</b><br>{_e(f['detail'])}<br>"
                f'<span class="muted">{_e(_where(f))} · {_e(f["kind"])}{tri}</span>'
                "</figcaption></figure>"
            )
        out.append("</div>")
        if len(fs) > MAX_EVIDENCE:
            more = "; ".join(f"{f['label']} ({_where(f)})" for f in fs[MAX_EVIDENCE:])
            out.append(
                f'<p class="muted" style="font-size:13px">…and {len(fs) - MAX_EVIDENCE} more: {_e(more)}</p>'
            )
        out.append("</section>")

    if model["best_practice"]:
        out.append("<h2>Platform guidelines (not WCAG failures)</h2><ul class='plain'>")
        for f in model["best_practice"]:
            out.append(
                f"<li><b>{_e(f['label'])}</b>: {_e(f['detail'])} <span class='muted'>({_e(f['screen'])})</span></li>"
            )
        out.append("</ul>")
    if model["wontfix"]:
        out.append("<h2>Accepted (won't fix)</h2><ul class='plain'>")
        for f in model["wontfix"]:
            out.append(
                f"<li>{_e(f['sc'] or '')} {_e(f['label'])}: {_e(f['detail'])} <span class='muted'>({_e(f['screen'])})</span></li>"
            )
        out.append("</ul>")

    # Criteria table
    out.append(f"<h2>All criteria (WCAG 2.2, Level {_e(model['level'])})</h2>")
    out.append(
        "<table><thead><tr><th>Criterion</th><th>Level</th><th>Status</th><th>How checked</th></tr></thead><tbody>"
    )
    principle = None
    for r in model["rows"]:
        if r["principle"] != principle:
            principle = r["principle"]
            out.append(f'<tr class="p"><td colspan="4">{_e(principle)}</td></tr>')
        tags = ('<span class="tag">2.2</span>' if r["new"] else "") + (
            '<span class="tag">advisory</span>' if r["advisory"] else ""
        )
        cnt = f' <span class="muted">({r["count"]})</span>' if r["count"] else ""
        out.append(
            f'<tr><td><a href="{_e(r["url"])}">{_e(r["sc"])}</a> {_e(r["name"])}{tags}</td><td>{_e(r["level"])}</td>'
            f'<td>{_pill(r["status"])}{cnt}</td><td class="muted">{_e(", ".join(r["how"]))}'
            + (f"<br><i>{_e(r['note'])}</i>" if r.get("note") else "")
            + "</td></tr>"
        )
    out.append("</tbody></table>")
    out.append(
        '<p class="muted" style="font-size:13px">'
        + " · ".join(f"{_pill(k)} {_e(v[1])}" for k, v in STATUS.items())
        + "</p>"
    )

    # Screens
    out.append("<h2>Screens audited</h2><div class='screens'>")
    for s in model["screens"]:
        thumb = run_dir / s["thumb"] if s.get("thumb") else None
        img = ""
        if thumb and thumb.is_file():
            img = f'<img alt="Screenshot of {_e(s["title"])}" src="data:image/jpeg;base64,{base64.b64encode(thumb.read_bytes()).decode()}">'
        badge = f' · <span class="bad">{s["issues"]}</span>' if s["issues"] else ""
        out.append(f"<figure>{img}<figcaption>{_e(s['id'])} · {_e(s['title'])}{badge}</figcaption></figure>")
    out.append("</div>")

    out.append(
        "<h2>Method and limits</h2><ul class='plain'>"
        "<li>The app was explored automatically on an emulator; screens not reached by the crawl were not checked.</li>"
        "<li>Sizes use density-independent pixels (dp ≈ CSS px). "
        + (
            "Density was read from the device."
            if model["audit"]["density_exact"]
            else "Density was <b>estimated</b> from screen width."
        )
        + "</li><li>Contrast, labels and other per-screen checks run in the web viewer; confirm them there to include them here.</li>"
        "<li>Criteria that need assistive technology, media, timing or judgement are marked <i>Not tested</i>. "
        "Run the device and manual steps in the <code>a11y-audit</code> skill to cover them.</li>"
        "<li>2.4.1, 2.4.5, 3.2.3, 3.2.4 and 3.2.6 are written for sets of web pages; for a single native app "
        "WCAG2ICT treats them as advisory.</li></ul>"
    )
    out.append("</main></body></html>")
    return "\n".join(out)


# ── Markdown ─────────────────────────────────────────────────────────────────


def render_md(model: dict, run_dir: Path) -> str:
    run, app, dev = model["run"], model["run"].get("app", {}), model["run"].get("device", {})
    screens = {s["id"]: s for s in load_map(run_dir)["screens"]}
    crops = run_dir / "a11y" / "crops"
    crops.mkdir(parents=True, exist_ok=True)
    for old in crops.glob("*.jpg"):
        old.unlink()
    sc_counts, total = model["status_counts"], len(model["rows"])
    lines = [
        f"# Accessibility report: {app.get('label') or app.get('package')}",
        "",
        (
            f"WCAG 2.2 Level {model['level']} · {app.get('package')} {app.get('version') or ''} · "
            f"{dev.get('manufacturer', '')} {dev.get('model', '')}, Android {dev.get('android', '?')} · run `{run.get('id')}` · "
            f"generated {model['generated_at']} by {model['tool']}"
        ),
        "",
        (
            "> Automated results are evidence for a person to confirm, **not a conformance claim**. Per-screen "
            "scanner checks (labels, contrast) run in the web viewer; only confirmed ones are included "
            f"({model['viewer_imported']} imported)."
        ),
        "",
        "## Summary",
        "",
        "| Status | Criteria |",
        "|---|---|",
        *[f"| {STATUS[k][0]} | {sc_counts.get(k, 0)} of {total} |" for k in STATUS],
        "",
        "## Findings by success criterion",
        "",
    ]
    rows = {r["sc"]: r for r in model["rows"]}
    order = {"fail": 0, "issues": 1, "review": 2}
    scs = sorted(model["findings_by_sc"], key=lambda sc: (order.get(rows[sc]["status"], 9), sc_key(sc)))
    if not scs:
        lines.append("_No findings at this level._\n")
    n = 0
    for sc in scs:
        r, fs = rows[sc], model["findings_by_sc"][sc]
        rule = RULES.get(fs[0]["rule"])
        tags = (" · new in 2.2" if r["new"] else "") + (
            " · advisory for native apps" if r["advisory"] else ""
        )
        lines += [f"### {sc} {r['name']} (Level {r['level']}) — {STATUS[r['status']][0]}{tags}", ""]
        if rule and fs[0]["source"] == "crawler":
            lines += [rule.why, "", f"**Fix:** {rule.fix}", ""]
        lines += ["| Screen | Element | Detail | Status | Evidence |", "|---|---|---|---|---|"]
        for f in fs:
            ev = ""
            if n < 200 and (img := _crop(run_dir, screens.get(f["screen"]), f)):
                n += 1
                name = f"{n:03d}.jpg"
                (crops / name).write_bytes(img)
                ev = f"![{f['label'][:30]}](a11y/crops/{name})"
            cell = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {cell(_where(f))} | {cell(f['label'])} | {cell(f['detail'])} | "
                f"{f['triage']} ({f['kind']}) | {ev} |"
            )
        lines += ["", f"[Understanding {sc}]({r['url']})", ""]
    if model["best_practice"]:
        lines += ["## Platform guidelines (not WCAG failures)", ""]
        lines += [f"- **{f['label']}**: {f['detail']} ({f['screen']})" for f in model["best_practice"]] + [""]
    lines += [
        f"## All criteria (Level {model['level']})",
        "",
        "| Criterion | Level | Status | How checked |",
        "|---|---|---|---|",
    ]
    for r in model["rows"]:
        tags = (" *(2.2)*" if r["new"] else "") + (" *(advisory)*" if r["advisory"] else "")
        cnt = f" ({r['count']})" if r["count"] else ""
        lines.append(
            f"| [{r['sc']}]({r['url']}) {r['name']}{tags} | {r['level']} | {STATUS[r['status']][0]}{cnt} | {', '.join(r['how'])}{' — ' + r['note'] if r.get('note') else ''} |"
        )
    lines += ["", "## Screens audited", ""]
    lines += [
        f"- {s['id']} · {s['title']}" + (f" — {s['issues']} finding(s)" if s["issues"] else "")
        for s in model["screens"]
    ]
    lines += [
        "",
        "## Method and limits",
        "",
        "- Explored automatically on an emulator; unreached screens were not checked.",
        "- Sizes in dp (≈ CSS px); density "
        + ("read from the device." if model["audit"]["density_exact"] else "estimated from screen width."),
        "- *Not tested* criteria need device or manual testing (see the `a11y-audit` skill).",
        "- 2.4.1, 2.4.5, 3.2.3, 3.2.4, 3.2.6 are advisory for a single native app under WCAG2ICT.",
        "",
    ]
    return "\n".join(lines)


def write_reports(run_dir: str | Path, level: str = "AA") -> dict:
    run_dir = Path(run_dir)
    model = build_model(run_dir, level)
    html_path = run_dir / "a11y-report.html"
    md_path = run_dir / "a11y-report.md"
    html_path.write_text(render_html(model, run_dir))
    md_path.write_text(render_md(model, run_dir))
    return {
        "html": str(html_path),
        "md": str(md_path),
        "status_counts": model["status_counts"],
        "findings": sum(len(v) for v in model["findings_by_sc"].values()),
    }
