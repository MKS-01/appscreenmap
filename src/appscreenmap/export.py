"""Exports from map.json: Maestro flows (one per screen) and a Mermaid flowchart."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import placeholders
from .model import load_map


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _regex_literal(s: str) -> str:
    """Maestro matches text selectors as regex; escape so labels match literally."""
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", s)


def _target(selector: dict, width: int, height: int) -> str:
    if selector.get("id"):
        return "{ id: " + _q(selector["id"]) + " }"
    if selector.get("text"):
        return _q(_regex_literal(selector["text"]))
    if selector.get("desc"):
        return _q(_regex_literal(selector["desc"]))
    x, y = selector.get("point", [0, 0])
    return "{ point: " + _q(f"{round(100 * x / max(width, 1))}%,{round(100 * y / max(height, 1))}%") + " }"


def _visible(selector: dict) -> str | None:
    if selector.get("id"):
        return "{ id: " + _q(selector["id"]) + " }"
    if selector.get("text"):
        return "{ text: " + _q(_regex_literal(selector["text"])) + " }"
    return None


def _assertion(screen: dict) -> str | None:
    """Pick something on the target screen that identifies it."""
    els = screen.get("elements", [])
    title = screen.get("title") or ""
    for e in els:
        if e.get("text") == title and title:
            return "- assertVisible: " + _q(_regex_literal(title))
    for e in els:
        if e.get("rid") and e.get("kind") not in ("list_item", "back") and e.get("action") != "scroll":
            return "- assertVisible: { id: " + _q(e["rid"]) + " }"
    if title:
        return "- assertVisible: " + _q(_regex_literal(title))
    return None


def maestro_flow(data: dict, screen: dict) -> str:
    app = data["run"]["app"]
    w, h = data["run"]["device"]["width"], data["run"]["device"]["height"]
    screens = {s["id"]: s for s in data["screens"]}
    lines = [
        f"# AppScreenMap: reach {screen['id']} — {screen.get('title', '')}",
        f"# Generated from run {data['run']['id']}",
        f"appId: {app['package']}",
        "---",
        "- launchApp:",
        "    stopApp: true",
    ]

    def autofill(sid: str):
        for f in screens.get(sid, {}).get("autofill", []):
            lines.append("- tapOn: " + _target(f["selector"], w, h))
            lines.append("- inputText: " + _q(f["value"]))
        if screens.get(sid, {}).get("autofill"):
            lines.append("- hideKeyboard")

    path_screens = [step["screen"] for step in screen.get("reach_path", [])]
    secrets = sorted(
        {
            n
            for sid in path_screens
            for f in screens.get(sid, {}).get("autofill", [])
            for n in placeholders(f["value"])
        }
    )
    if secrets:
        lines.insert(2, "# Needs: maestro test " + " ".join(f"-e {n}=…" for n in secrets))

    for step in screen.get("reach_path", []):
        autofill(step["screen"])
        lines.append(f"# on {step['screen']}: {step['action']} '{step['label']}'")
        sel = step["selector"]
        if step["action"] == "back":
            lines.append("- back")
            continue
        if step.get("scroll_depth") and (vis := _visible(sel)):
            lines.append("- scrollUntilVisible:")
            lines.append(f"    element: {vis}")
            lines.append("    direction: DOWN")
        cmd = "longPressOn" if step["action"] == "long_click" else "tapOn"
        lines.append(f"- {cmd}: " + _target(sel, w, h))
    if a := _assertion(screen):
        lines.append(a)
    lines.append(f"- takeScreenshot: {screen['id']}")
    return "\n".join(lines) + "\n"


def mermaid(data: dict) -> str:
    out = ["flowchart LR"]
    for s in data["screens"]:
        title = (s.get("title") or s["id"]).replace('"', "'")
        nid = s["id"].replace(":", "_").replace(".", "_")
        shape = f'{nid}(["{title}"])' if s["kind"] != "app" else f'{nid}["{s["id"]} · {title}"]'
        out.append(f"  {shape}")
    for t in data["transitions"]:
        a = t["from"].replace(":", "_").replace(".", "_")
        b = t["to"].replace(":", "_").replace(".", "_")
        label = (t.get("label") or t["action"]).replace('"', "'")[:30]
        out.append(f'  {a} -->|"{label}"| {b}')
    return "\n".join(out) + "\n"


def export_run(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    data = load_map(run_dir)
    flows = run_dir / "flows"
    flows.mkdir(exist_ok=True)
    count, skipped = 0, []
    for s in data["screens"]:
        if s["kind"] != "app":
            continue
        if s.get("origin") == "unknown":
            skipped.append(s["id"])  # no recorded path: a flow would only launch the app
            (flows / f"{s['id']}.yaml").unlink(missing_ok=True)
            continue
        (flows / f"{s['id']}.yaml").write_text(maestro_flow(data, s))
        count += 1
    (run_dir / "map.mmd").write_text(mermaid(data))
    return {"flows": count, "skipped": skipped, "mermaid": str(run_dir / "map.mmd")}
