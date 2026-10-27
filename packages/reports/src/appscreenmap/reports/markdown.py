"""The report as Markdown: `report.md` plus `report-assets/` (screen thumbnails), for PRs and repos."""

from __future__ import annotations

import shutil
from pathlib import Path

SEV = {"error": "Error", "warning": "Warning", "info": "Info"}


def esc(s) -> str:
    """Text safe inside a Markdown table cell."""
    return str("" if s is None else s).replace("|", "\\|").replace("\n", " ")


def link(ref: dict) -> str:
    pub = f" ({ref['publisher']})" if ref.get("publisher") else ""
    return f"[{ref.get('title') or ref['url']}]({ref['url']}){pub}"


def where_text(f: dict) -> str:
    return ", ".join(f"{w['id']} {w['title']}" for w in f.get("where") or [])


def _score(s: dict) -> str:
    return "—" if s.get("score") is None else str(s["score"])


def _chart(c: dict) -> list[str]:
    unit = f" ({c['unit']})" if c.get("unit") else ""
    out = [
        f"**{c['title']}**{' · ' + c['note'] if c.get('note') else ''}",
        "",
        f"| | Value{unit} |",
        "|---|---:|",
    ]
    out += [f"| {esc(d['label'])} | {esc(d['value'])} |" for d in c["data"]]
    if c.get("budget") is not None:
        out.append(f"| *{esc(c.get('budgetLabel') or 'budget')}* | {c['budget']} |")
    return out + [""]


def render(doc: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    assets = out_dir / "report-assets"
    run = Path(doc["run_dir"])
    used: dict[str, str] = {}

    def thumb(w: dict) -> str | None:
        if not w.get("image"):
            return None
        if w["id"] not in used:
            assets.mkdir(parents=True, exist_ok=True)
            name = f"{w['id']}{Path(w['image']).suffix}"
            shutil.copyfile(run / w["image"], assets / name)
            used[w["id"]] = f"report-assets/{name}"
        return used[w["id"]]

    c = doc["cover"]
    L = [
        "| | |",
        "|---|---|",
        f"| App | {esc(c['app'])} |",
        f"| Package | `{c['package']}` |" if c.get("package") else "",
        f"| Version | {esc(c['version'])} |" if c.get("version") else "",
        f"| Platform | {esc(c['platform'])} |",
        f"| Canvas | `{c['canvas']}` · {c['screens']} screens |",
        f"| Crawled | {esc(c['crawled'])} |" if c.get("crawled") else "",
        f"| Report | {doc['generated_at']} · {doc['tool']} · profile `{doc['profile']}` |",
        "",
    ]
    L = [f"# {doc['title']}", ""] + [x for x in L if x != ""] + [""]

    L += [
        "## Summary",
        "",
        "| Audit | Status | Score | Errors | Warnings | Info | Summary |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for s in doc["summary"]:
        n = s["counts"]
        L.append(
            f"| [{esc(s['title'])}](#{s['id']}) | {esc(s['status_word'])} | {_score(s)} | {n['error']} | {n['warning']} | {n['info']} | {esc(s['summary'])} |"
        )
    L.append("")
    if doc["top"]:
        L += ["### Top findings", ""]
        L += [
            f"{i}. **{SEV[f['severity']]}** · {esc(f['title'])} · {f['audit_title']}"
            + (f" · {where_text(f)}" if f.get("where") else "")
            + (f" · due {f['due']}" if f.get("due") else "")
            for i, f in enumerate(doc["top"], 1)
        ]
        L.append("")
    if doc["deadlines"]:
        L += ["### Deadlines", "", "| Due | Finding | Audit | State |", "|---|---|---|---|"]
        L += [
            f"| {f['due']} | {esc(f['title'])} | {esc(f['audit_title'])} | {esc(f.get('requirement') or '')} |"
            for f in doc["deadlines"]
        ]
        L.append("")

    cond = doc["conditions"]
    L += ["## Conditions", ""]
    if cond["device"]:
        L += [f"Captured on {cond['device']}.", "", "| | |", "|---|---|"]
        L += [f"| {esc(k)} | {esc(v)} |" for k, v in cond["rows"]]
        L.append("")
    if cond["scenarios"]:
        L += ["| Scenario | Run | Screens |", "|---|---|---:|"]
        L += [
            f"| {esc(sc['label'] or sc['id'])} | `{sc['run'] or ''}` | {sc['screens']} |"
            for sc in cond["scenarios"]
        ]
        L.append("")

    for s in doc["sections"]:
        L += [f'<a id="{s["id"]}"></a>', "", f"## {s['title']}", ""]
        L.append(f"**{s['status_word']}** · score {_score(s)}" + (f" · {s['tool']}" if s.get("tool") else ""))
        L += ["", s["summary"], ""]
        if s.get("score_note"):
            L += [f"*Score: {s['score_note']}*", ""]
        if s["metrics"]:
            L += ["| Metric | Value |", "|---|---:|"]
            L += [
                f"| {esc(m['label'])} | {esc(m['value'])}{(' ' + m['unit']) if m.get('unit') else ''} |"
                for m in s["metrics"]
            ]
            L.append("")
        for ch in s["charts"]:
            L += _chart(ch)
        if not s["findings"]:
            L += ["No findings." if s["status"] != "not_run" else "Not run.", ""]
        for cat, fs in s["groups"].items():
            if len(fs) > 1:
                L += [f"### {cat}", ""]
            for f in fs:
                L += [f"#### {SEV[f['severity']]} · {f['title']}", ""]
                meta = [f"`{f['id']}`"] + ([cat] if len(fs) == 1 else [])
                if f.get("platform"):
                    meta.append(f["platform"])
                if f.get("due"):
                    meta.append(f"due {f['due']}")
                if f.get("requirement"):
                    meta.append(f"requirement: {f['requirement']}")
                if f.get("triage"):
                    meta.append(f"triage: {f['triage'].replace('_', ' ')}")
                L += [" · ".join(meta), ""]
                if f.get("detail"):
                    L += [f["detail"], ""]
                if f.get("items"):
                    L += [f"- {esc(t)}" for t in f["items"]] + [""]
                if f.get("where"):
                    L.append(f"**Where:** {where_text(f)}")
                    imgs = [(w, thumb(w)) for w in f["where"][:4]]
                    if any(p for _, p in imgs):
                        L += ["", " ".join(f"![{esc(w['title'])}]({p})" for w, p in imgs if p)]
                    L.append("")
                if f.get("fix"):
                    L += [f"**Fix:** {f['fix']}", ""]
                if f.get("refs"):
                    L += ["**Sources:** " + " · ".join(link(r) for r in f["refs"]), ""]
        if s["manual"]:
            L += ["### Not tested (manual checks)", ""]
            L += [
                f"- **{esc(m.get('title'))}**: {esc(m.get('steps') or m.get('detail') or '')}"
                for m in s["manual"]
            ]
            L.append("")

    ap = doc["appendix"]
    L += ["## Appendix", "", "### Method", ""] + [f"- {m}" for m in ap["method"]] + [""]
    if ap["sources"]:
        L += ["### Sources", ""] + [f"- {link(r)}" for r in ap["sources"]] + [""]
    L += ["### Glossary", ""] + [f"- **{k}**: {v}" for k, v in ap["glossary"]] + [""]

    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "report.md"
    p.write_text("\n".join(L))
    return p
