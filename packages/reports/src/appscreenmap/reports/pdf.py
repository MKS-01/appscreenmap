"""The report as PDF: the HTML report on light paper, printed by headless Chrome / Chromium. No new dependency.

`APPSCREENMAP_CHROME` points at a browser binary when it isn't in a usual place. `doctor` reports what it found.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from . import htmldoc

PAPER = {"a4": "A4", "letter": "letter"}
INSTALL = "install Google Chrome or Chromium, or set APPSCREENMAP_CHROME to its binary"
_MAC_APPS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "microsoft-edge")
TIMEOUT_S = 120


class PdfError(RuntimeError):
    pass


def find_chrome() -> str | None:
    env = os.environ.get("APPSCREENMAP_CHROME")
    if env:
        return env if Path(env).is_file() else None  # render() names the missing override
    for p in _MAC_APPS:
        if Path(p).is_file():
            return p
    return next((w for n in _NAMES if (w := shutil.which(n))), None)


# Paper is the one exception to dark only (owner, 2026-10-28): the semantic tokens point at tokens.css's --print-*.
PAPER_TOKENS = (
    "bg", "panel", "panel-2", "line", "line-hi", "text", "dim", "faint", "accent", "good", "warn", "bad", "info",
    "good-14", "warn-14", "bad-14", "info-14",
)  # fmt: skip


def page_margin() -> str:
    m = re.search(r"--print-page-margin:\s*([^;]+);", htmldoc.tokens_css())
    return m.group(1).strip() if m else "14mm 12mm"


def print_css(paper: str) -> str:
    """Paper size, page breaks, and the light print palette: the screen version stays dark."""
    remap = "".join(f"--{t}:var(--print-{t});" for t in PAPER_TOKENS)
    return (
        f"@page{{size:{PAPER[paper]};margin:{page_margin()}}}"
        "@media print{"
        f":root{{color-scheme:light;{remap}--accent-hi:var(--print-accent)}}"
        "html,body{background:var(--bg)}"
        "*{print-color-adjust:exact;-webkit-print-color-adjust:exact}"
        # Chrome clips a border that sits exactly on the printable edge: keep a token's width inside it.
        "main{max-width:none;padding:0 var(--space-1)}"
        "a{text-decoration:none}"
        "h2,h3,h4{break-after:avoid}"
        ".sec,.metrics,.finding,.card,.chart,tr,figure{break-inside:avoid}"
        "thead{display:table-header-group}"
        "th.wide:last-child,td.wide.dim{width:32%}"
        ".sec{break-after:avoid}.gallery{grid-template-columns:repeat(7,1fr)}.evidence figure{width:150px}"
        ".tw{overflow:visible}"
        "}"
    )


def render(doc: dict, out_dir: Path, paper: str = "a4") -> Path:
    out_dir = Path(out_dir)
    out = out_dir / "report.pdf"
    out.unlink(missing_ok=True)  # never mistake last run's file for this one, even when this one fails
    chrome = find_chrome()
    if not chrome:
        env = os.environ.get("APPSCREENMAP_CHROME")
        raise PdfError(
            f"APPSCREENMAP_CHROME={env} doesn't exist" if env else f"no Chrome or Chromium found: {INSTALL}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    src = out_dir / ".report-print.html"
    src.write_text(htmldoc.page(doc, print_css(paper)))
    try:
        r = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw",
                f"--print-to-pdf={out}",
                src.resolve().as_uri(),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as ex:
        raise PdfError(f"Chrome took over {TIMEOUT_S} s to print the report") from ex
    except OSError as ex:  # not executable, wrong architecture
        raise PdfError(f"couldn't start {chrome}: {ex}") from ex
    finally:
        src.unlink(missing_ok=True)
    if r.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        said = (r.stderr or r.stdout).strip()[-400:]
        raise PdfError(f"Chrome couldn't print the report (exit {r.returncode}){': ' + said if said else ''}")
    return out
