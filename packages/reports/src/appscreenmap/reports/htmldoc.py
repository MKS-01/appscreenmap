"""The report as one self-contained HTML file: design tokens and screen thumbnails inlined, opens offline.

Styled only through `packages/design-tokens/tokens.css` (the design-system skill), read at report time.
"""

from __future__ import annotations

import base64
import html
from importlib import resources
from pathlib import Path

SEV = {"error": "Error", "warning": "Warning", "info": "Info"}
# A colour never stands alone (design-system rule 4): every toned value carries one of these words.
TONE_WORD = {"good": "good", "warn": "needs work", "bad": "poor", "info": "info"}
FONTS = (
    ("Geist Variable", "geist-latin-wght-normal.woff2"),
    ("Geist Mono Variable", "geist-mono-latin-wght-normal.woff2"),
)
TONE = {"pass": "good", "warn": "warn", "fail": "bad", "info": "info", "not_run": "info"}
SEV_TONE = {"error": "bad", "warning": "warn", "info": "info"}
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def tokens_css() -> str:
    """The wheel ships tokens.css as `appscreenmap/design/tokens.css`; a checkout reads it from the repo."""
    try:
        return resources.files("appscreenmap.design").joinpath("tokens.css").read_text()
    except (ModuleNotFoundError, FileNotFoundError, OSError, TypeError):
        pass
    p = Path(__file__).resolve().parents[4] / "design-tokens" / "tokens.css"
    return p.read_text() if p.is_file() else ""


def fonts_css() -> str:
    """Geist and Geist Mono (OFL, latin subset, `fonts/OFL.txt`) inlined, so the file looks the same offline."""
    out = []
    for family, name in FONTS:
        p = Path(__file__).with_name("fonts") / name
        if p.is_file():
            data = base64.b64encode(p.read_bytes()).decode()
            out.append(
                f'@font-face{{font-family:"{family}";font-style:normal;font-display:swap;font-weight:100 900;'
                f'src:url(data:font/woff2;base64,{data}) format("woff2")}}'
            )
    return "".join(out)


CSS = """
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:var(--weight-regular) var(--text-md)/var(--leading-normal) var(--font-sans)}
main{max-width:var(--measure);margin:0 auto;padding:var(--space-7) var(--space-5)}
h1,h2,h3,h4{font-weight:var(--weight-semibold);letter-spacing:var(--tracking-tight)}
h1{font-size:var(--text-3xl);line-height:var(--leading-tight);margin:0 0 var(--space-2)}
h2{font-size:var(--text-xl);line-height:var(--leading-snug);margin:var(--space-7) 0 var(--space-3);padding-top:var(--space-5);border-top:1px solid var(--line)}
h3{font-size:var(--text-lg);line-height:var(--leading-snug);margin:var(--space-5) 0 var(--space-2)}
a{color:var(--accent);text-decoration:none}a:hover{color:var(--accent-hi);text-decoration:underline}
code,.mono{font-family:var(--font-mono);font-size:var(--text-sm);overflow-wrap:anywhere}
main *{min-width:0}p,li,h4{overflow-wrap:anywhere}td{overflow-wrap:break-word}
.kicker{font:var(--weight-regular) var(--text-xs)/var(--leading-snug) var(--font-mono);text-transform:uppercase;letter-spacing:var(--tracking-label);color:var(--faint);margin:0 0 var(--space-2)}
.toc{display:flex;flex-wrap:wrap;gap:var(--space-1) var(--space-3);font-size:var(--text-sm);margin:0 0 var(--space-5)}
.dim{color:var(--dim)}.faint{color:var(--faint)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-md);padding:var(--space-4)}
table{width:100%;border-collapse:collapse;font-size:var(--text-base)}
th{text-align:left;font:var(--weight-regular) var(--text-xs)/var(--leading-snug) var(--font-mono);text-transform:uppercase;letter-spacing:var(--tracking-label);color:var(--faint)}
th,td{padding:var(--space-2) var(--space-3);border-bottom:1px solid var(--line);vertical-align:top}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:var(--space-2) var(--space-5);margin:var(--space-4) 0}
.facts div{border-top:1px solid var(--line);padding-top:var(--space-2)}
.chip{display:inline-flex;align-items:center;gap:var(--space-2);font:var(--weight-regular) var(--text-xs)/var(--leading-snug) var(--font-mono);padding:var(--space-1) var(--space-2);border-radius:var(--radius-sm);white-space:nowrap}
.chip::before{content:"";width:var(--space-2);height:var(--space-2);border-radius:var(--radius-pill);background:currentColor}
.good{color:var(--good)}.warn{color:var(--warn)}.bad{color:var(--bad)}.info{color:var(--info)}
.chip.good{background:var(--good-14)}.chip.warn{background:var(--warn-14)}.chip.bad{background:var(--bad-14)}.chip.info{background:var(--info-14)}
.head{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--space-3);margin-bottom:var(--space-2)}
.score{font:var(--weight-semibold) var(--text-xl)/var(--leading-tight) var(--font-sans)}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:var(--space-2);margin:var(--space-4) 0}
.metrics .card{padding:var(--space-3)}.metrics b{display:block;font-size:var(--text-lg);font-weight:var(--weight-semibold)}
.metrics .word{font:var(--text-xs)/var(--leading-snug) var(--font-mono);margin-top:var(--space-1)}
.chart{margin:var(--space-4) 0}
.bar{display:grid;grid-template-columns:minmax(120px,30%) 1fr minmax(96px,auto);gap:var(--space-3);align-items:center;font-size:var(--text-sm);padding:var(--space-1) 0}
.bar .track{height:var(--space-2);background:var(--panel-2);border-radius:var(--radius-sm);position:relative}
.bar .fill{height:100%;border-radius:var(--radius-sm);background:var(--dim)}
.bar .fill.good{background:var(--good)}.bar .fill.warn{background:var(--warn)}.bar .fill.bad{background:var(--bad)}.bar .fill.info{background:var(--info)}
.bar .budget{position:absolute;top:calc(-1 * var(--space-1));bottom:calc(-1 * var(--space-1));width:1px;background:var(--text)}
.finding{border-top:1px solid var(--line);padding:var(--space-4) 0;display:grid;grid-template-columns:1fr auto;gap:var(--space-4);align-items:start}
.finding h4{margin:0 0 var(--space-1);font-size:var(--text-md)}
.finding p{margin:var(--space-1) 0}.finding ul{margin:var(--space-1) 0;padding-left:var(--space-5);color:var(--dim)}
.meta{display:flex;flex-wrap:wrap;gap:var(--space-2);align-items:center;color:var(--faint);font:var(--text-xs)/var(--leading-snug) var(--font-mono)}
.shots{display:flex;gap:var(--space-2)}
.shots figure{margin:0;width:64px}
.shots img{width:100%;display:block;border-radius:var(--radius-md)}
.frame{padding:var(--space-1);border:1px solid var(--line-hi);border-radius:var(--radius-lg);background:var(--panel-2)}
.shots figcaption{font:var(--text-xs)/var(--leading-snug) var(--font-mono);color:var(--faint);margin-top:var(--space-1);overflow-wrap:anywhere}
ol.top li{margin:var(--space-1) 0}
.tw{overflow-x:auto;max-width:100%}.narrow{display:none;font-size:var(--text-sm);margin-top:var(--space-1)}
@media (max-width:640px){main{padding:var(--space-5) var(--space-4)}.wide{display:none}.narrow{display:block}th,td{padding:var(--space-2)}.finding{grid-template-columns:1fr}.bar{grid-template-columns:1fr auto}.bar .track{grid-column:1/-1;grid-row:2}}
"""


def e(s) -> str:
    return html.escape(str("" if s is None else s))


def _img(run: Path, rel: str) -> str | None:
    p = run / rel
    try:
        data = base64.b64encode(p.read_bytes()).decode()
    except OSError:
        return None
    return f"data:{MIME.get(p.suffix.lower(), 'image/png')};base64,{data}"


def _word(tone: str | None) -> str:
    return f" · {TONE_WORD[tone]}" if tone in TONE_WORD else ""


def _chip(tone: str, word: str) -> str:
    return f'<span class="chip {tone}">{e(word)}</span>'


def _chart(c: dict) -> str:
    data = c["data"]
    hi = max([d["value"] for d in data] + [c.get("budget") or 0]) or 1
    unit = f" {c['unit']}" if c.get("unit") else ""
    if c["type"] == "split":
        total = sum(d["value"] for d in data) or 1
        rows = "".join(
            f'<div class="bar"><span>{e(d["label"])}</span><div class="track"><div class="fill {d.get("tone", "")}" style="width:{100 * d["value"] / total:.1f}%"></div></div><span class="mono n">{d["value"]} · {round(100 * d["value"] / total)}%</span></div>'
            for d in data
        )
    else:
        budget = (
            f'<div class="budget" style="left:{100 * c["budget"] / hi:.1f}%"></div>'
            if c.get("budget") is not None
            else ""
        )
        rows = "".join(
            f'<div class="bar"><span>{e(d["label"])}</span><div class="track"><div class="fill {d.get("tone", "")}" style="width:{100 * d["value"] / hi:.1f}%"></div>{budget}</div><span class="mono {d.get("tone", "")}">{e(d["value"])}{e(unit)}{_word(d.get("tone"))}</span></div>'
            for d in data
        )
    note = " · ".join(x for x in (c.get("note"), c.get("budgetLabel")) if x)
    return f'<div class="chart"><p class="kicker">{e(c["title"])}{(" · " + e(note)) if note else ""}</p>{rows}</div>'


def _refs(refs: list[dict]) -> str:
    return " · ".join(f'<a href="{e(r["url"])}">{e(r.get("title") or r["url"])}</a>' for r in refs)


def _finding(f: dict, run: Path, cache: dict, category: str | None = None) -> str:
    meta = [_chip(SEV_TONE[f["severity"]], SEV[f["severity"]]), f"<code>{e(f['id'])}</code>"]
    if category:
        meta.append(e(category))
    meta += [e(x) for x in (f.get("platform"), f"due {f['due']}" if f.get("due") else None) if x]
    if f.get("requirement"):
        meta.append(f"requirement: {e(f['requirement'])}")
    if f.get("triage"):
        meta.append(f"triage: {e(f['triage'].replace('_', ' '))}")
    body = [
        f"<h4>{e(f['title'])}</h4>",
        f'<div class="meta">{"".join(f"<span>{m}</span>" for m in meta)}</div>',
    ]
    if f.get("detail"):
        body.append(f'<p class="dim">{e(f["detail"])}</p>')
    if f.get("items"):
        body.append("<ul>" + "".join(f"<li>{e(t)}</li>" for t in f["items"]) + "</ul>")
    if f.get("where"):
        # A folded row already names each screen in its list: the ids are enough here.
        names = [w["id"] if f.get("items") else f"{w['id']} {w['title']}" for w in f["where"]]
        body.append(f"<p><b>Where:</b> {e(', '.join(names))}</p>")
    if f.get("fix"):
        body.append(f"<p><b>Fix:</b> {e(f['fix'])}</p>")
    if f.get("refs"):
        body.append(f"<p><b>Sources:</b> {_refs(f['refs'])}</p>")
    shots = []
    for w in (f.get("where") or [])[:3]:
        if w.get("image"):
            if w["id"] not in cache:
                cache[w["id"]] = _img(run, w["image"])
            if cache[w["id"]]:
                shots.append(
                    f'<figure><div class="frame"><img src="{cache[w["id"]]}" alt="{e(w["title"])}"></div><figcaption>{e(w["id"])}</figcaption></figure>'
                )
    side = f'<div class="shots">{"".join(shots)}</div>' if shots else "<div></div>"
    return f'<div class="finding"><div>{"".join(body)}</div>{side}</div>'


def render(doc: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    run = Path(doc["run_dir"])
    cache: dict[str, str | None] = {}
    c = doc["cover"]
    H = [
        f'<p class="kicker">AppScreenMap report · {e(doc["profile"])}</p>',
        f"<h1>{e(c['app'])}</h1>",
        '<nav class="toc">'
        + "".join(
            f'<a href="#{e(i)}">{e(t)}</a>'
            for i, t in [("summary", "Summary"), ("conditions", "Conditions")]
            + [(s["id"], s["title"]) for s in doc["sections"]]
            + [("appendix", "Appendix")]
        )
        + "</nav>",
        '<div class="facts">',
    ]
    for k, v in (
        ("Package", c.get("package")),
        ("Version", c.get("version")),
        ("Platform", c.get("platform")),
        ("Canvas", f"{c['canvas']} · {c['screens']} screens"),
        ("Crawled", c.get("crawled")),
        ("Report", f"{doc['generated_at']} · {doc['tool']}"),
    ):
        if v:
            H.append(f'<div><p class="kicker">{k}</p><span class="mono">{e(v)}</span></div>')
    H.append("</div>")

    H += [
        '<h2 id="summary">Summary</h2>',
        '<table><tr><th>Audit</th><th>Status</th><th class="n">Score</th><th class="n wide">Errors</th><th class="n wide">Warnings</th><th class="n wide">Info</th><th class="wide">Summary</th></tr>',
    ]
    for s in doc["summary"]:
        n = s["counts"]
        H.append(
            f'<tr><td><a href="#{e(s["id"])}">{e(s["title"])}</a><div class="narrow dim">{e(s["summary"])}</div></td><td>{_chip(TONE.get(s["status"], "info"), s["status_word"])}</td>'
            f'<td class="n">{"—" if s["score"] is None else s["score"]}</td><td class="n wide">{n["error"]}</td><td class="n wide">{n["warning"]}</td>'
            f'<td class="n wide">{n["info"]}</td><td class="dim wide">{e(s["summary"])}</td></tr>'
        )
    H.append("</table>")
    if doc["top"]:
        H.append('<h3>Top findings</h3><ol class="top">')
        H += [
            f'<li>{_chip(SEV_TONE[f["severity"]], SEV[f["severity"]])} {e(f["title"])} <span class="faint">· {e(f["audit_title"])}'
            + (f" · {e(', '.join(w['title'] for w in f['where']))}" if f.get("where") else "")
            + (f" · due {e(f['due'])}" if f.get("due") else "")
            + "</span></li>"
            for f in doc["top"]
        ]
        H.append("</ol>")
    if doc["deadlines"]:
        H.append("<h3>Deadlines</h3><table><tr><th>Due</th><th>Finding</th><th>Audit</th><th>State</th></tr>")
        H += [
            f'<tr><td class="mono">{e(f["due"])}</td><td>{e(f["title"])}</td><td>{e(f["audit_title"])}</td><td>{e(f.get("requirement") or "")}</td></tr>'
            for f in doc["deadlines"]
        ]
        H.append("</table>")

    cond = doc["conditions"]
    H.append('<h2 id="conditions">Conditions</h2>')
    if not cond["device"] and not cond["scenarios"]:
        H.append('<p class="dim">No device facts recorded for this canvas.</p>')
    if cond["device"]:
        H.append(f'<p class="dim">Captured on {e(cond["device"])}.</p><table>')
        H += [f'<tr><td class="faint">{e(k)}</td><td>{e(v)}</td></tr>' for k, v in cond["rows"]]
        H.append("</table>")
    if cond["scenarios"]:
        H.append('<h3>Scenarios</h3><table><tr><th>Scenario</th><th>Run</th><th class="n">Screens</th></tr>')
        H += [
            f'<tr><td>{e(sc["label"] or sc["id"])}</td><td class="mono">{e(sc["run"])}</td><td class="n">{sc["screens"]}</td></tr>'
            for sc in cond["scenarios"]
        ]
        H.append("</table>")

    for s in doc["sections"]:
        H.append(f'<h2 id="{e(s["id"])}">{e(s["title"])}</h2>')
        score = f'<span class="score">{s["score"]}</span>' if s["score"] is not None else ""
        H.append(
            f'<div class="head">{score}{_chip(TONE.get(s["status"], "info"), s["status_word"])}<span class="faint mono">{e(s.get("tool") or "")}</span></div>'
        )
        H.append(f"<p>{e(s['summary'])}</p>")
        if s.get("score_note"):
            H.append(f'<p class="faint">Score: {e(s["score_note"])}</p>')
        if s["metrics"]:
            H.append('<div class="metrics">')
            H += [
                f'<div class="card"><p class="kicker">{e(m["label"])}</p><b>{e(m["value"])}{(" " + e(m["unit"])) if m.get("unit") else ""}</b>'
                + (
                    f'<div class="word {m["tone"]}">{TONE_WORD[m["tone"]]}</div>'
                    if m.get("tone") in TONE_WORD
                    else ""
                )
                + "</div>"
                for m in s["metrics"]
            ]
            H.append("</div>")
        H += [_chart(ch) for ch in s["charts"]]
        if not s["findings"]:
            H.append(f'<p class="dim">{"Not run." if s["status"] == "not_run" else "No findings."}</p>')
        for cat, fs in s["groups"].items():
            if len(fs) > 1:
                H.append(f"<h3>{e(cat)}</h3>")
            H += [_finding(f, run, cache, None if len(fs) > 1 else cat) for f in fs]
        if s["manual"]:
            H.append("<h3>Not tested (manual checks)</h3><ul>")
            H += [
                f"<li><b>{e(m.get('title'))}</b>: {e(m.get('steps') or m.get('detail') or '')}</li>"
                for m in s["manual"]
            ]
            H.append("</ul>")

    ap = doc["appendix"]
    H.append(
        '<h2 id="appendix">Appendix</h2><h3>Method</h3><ul>'
        + "".join(f"<li>{e(m)}</li>" for m in ap["method"])
        + "</ul>"
    )
    if ap["sources"]:
        H.append(
            "<h3>Sources</h3><ul>"
            + "".join(
                f'<li><a href="{e(r["url"])}">{e(r.get("title") or r["url"])}</a> <span class="faint">{e(r.get("publisher") or "")}</span></li>'
                for r in ap["sources"]
            )
            + "</ul>"
        )
    if ap["glossary"]:
        H.append(
            "<h3>Glossary</h3><table>"
            + "".join(f"<tr><td><b>{e(k)}</b></td><td>{e(v)}</td></tr>" for k, v in ap["glossary"])
            + "</table>"
        )

    body = "".join(H).replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{e(doc['title'])}</title><style>{fonts_css()}{tokens_css()}{CSS}</style></head>"
        f"<body><main>{body}</main></body></html>\n"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "report.html"
    p.write_text(page)
    return p
