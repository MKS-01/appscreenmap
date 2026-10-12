"""`appscreenmap verify`: replay every screen's recorded path on a new build and report what broke.

Each screen with a recorded path is replayed from a fresh launch, longest paths first; screens passed
on the way count as checked, so most screens cost no extra launch. A path fails when a step's element
is missing, or a step leads to a different screen, out of the app, or to a crash. Screens behind a
failed step are reported as blocked (not replayed again). Every screen reached is captured and
compared with the base run (pixels and text), so a path that still works but looks different shows
up as changed.

Output, inside the base run: verify/<verify-id>/
    verify.json          results (docs/MAP_SCHEMA.md)
    screens/s003.png     the screen as the new build shows it (+ .xml hierarchy)
    failed/s005.png      where a path broke (+ .xml)
    diff/s003.png        visual diff against the base screenshot
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from .analyzer import analyze
from .config import placeholders
from .driver import DriverError
from .media import save_thumbnail
from .model import load_map, write_json_atomic
from .replay import MATCH_THRESHOLD, Replayer, ReplayFailed
from .visual import compare_images, screen_text_diff, text_changed

CHANGED_ABOVE = 0.002  # changed pixel ratio above which a screen counts as visually changed (as in diff)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def origin(screen: dict) -> str:
    # Maps written before `origin` existed: an empty path means launch lands there.
    return screen.get("origin") or ("action" if screen.get("reach_path") else "launch")


def plan(data: dict, only: list[str] | None = None) -> tuple[list[str], list[str]]:
    """(screens to replay, longest path first; screens without a recorded path)."""
    app = [s for s in data["screens"] if s["kind"] == "app" and (not only or s["id"] in only)]
    skipped = [s["id"] for s in app if origin(s) == "unknown"]
    targets = sorted(
        (s for s in app if origin(s) != "unknown"), key=lambda s: (-len(s.get("reach_path") or []), s["id"])
    )
    return [s["id"] for s in targets], skipped


def required_secrets(data: dict) -> list[str]:
    """Environment variables the recorded form inputs need."""
    return sorted(
        {
            n
            for s in data["screens"]
            for f in s.get("autofill") or []
            for n in placeholders(f.get("value", ""))
        }
    )


def verify_run(
    base_dir: str | Path,
    driver,
    clear_data: bool | None = None,
    only: list[str] | None = None,
    threshold: float = MATCH_THRESHOLD,
    out_dir: str | Path | None = None,
    log=print,
) -> dict:
    base_dir = Path(base_dir)
    data = load_map(base_dir)
    cfg = data["run"].get("config", {})
    clear = cfg.get("clear_data", False) if clear_data is None else clear_data
    vid = "verify-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(out_dir) if out_dir else base_dir / "verify" / vid
    for sub in ("screens", "failed", "diff"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    screens = {s["id"]: s for s in data["screens"]}
    pkg = data["run"]["app"]["package"]
    targets, skipped = plan(data, only)

    report: dict = {
        "schema": 1,
        "id": vid,
        "base_run": data["run"]["id"],
        "status": "running",
        "started_at": _now(),
        "finished_at": None,
        "app": {"package": pkg, "version": driver.app_version(pkg)},
        "base_app": data["run"]["app"],
        "device": driver.info(),
        "clear_data": clear,
        "threshold": threshold,
    }
    results: dict[str, dict] = {
        sid: {
            "screen": sid,
            "title": screens[sid].get("title"),
            "status": "skipped",
            "note": "no recorded path",
        }
        for sid in skipped
    }
    failed_prefixes: dict[tuple, str] = {}  # (screen, key) steps up to a broken one → the screen it broke
    rp = Replayer(driver, data, threshold, measure=cfg.get("measure_load", True), log=log)

    anim = None
    font = None
    if cfg.get("disable_animations", True):
        anim = driver.get_animations()
        driver.set_animations(0)
    if cfg.get("font_scale"):
        font = driver.get_font_scale()
        driver.set_font_scale(cfg["font_scale"])
    try:
        for target in targets:
            if target in results:
                continue
            path = screens[target].get("reach_path") or []
            keys = tuple((st["screen"], st["key"]) for st in path)
            blocker = next((sid for fp, sid in failed_prefixes.items() if keys[: len(fp)] == fp), None)
            if blocker is not None:
                results[target] = {
                    "screen": target,
                    "title": screens[target].get("title"),
                    "status": "blocked",
                    "blocked_by": blocker,
                    "path": [st["screen"] for st in path],
                }
                continue
            expected = [st["screen"] for st in path] + [target]
            log(f"▶ {target} {screens[target].get('title')!r} ({len(path)} step{'s' * (len(path) != 1)})")

            def on_arrival(a, expected=expected, path=path):
                if a.screen in results:
                    return
                safe = a.screen.replace(":", "_")
                driver.screenshot(out / "screens" / f"{safe}.png")
                (out / "screens" / f"{safe}.xml").write_text(a.obs.xml)
                results[a.screen] = {
                    "screen": a.screen,
                    "title": screens[a.screen].get("title"),
                    "status": "passed",
                    "path": expected[: a.index],
                    "similarity": a.similarity,
                    "load_ms": a.load_ms,
                    "via": a.via or None,
                    "screenshot": f"screens/{safe}.png",
                    "hierarchy": f"screens/{safe}.xml",
                    "_obs": a.obs,
                }
                log(f"  ✔ {a.screen} {screens[a.screen].get('title')!r} ({a.similarity:.0%})")

            try:
                rp.replay(target, clear_data=clear, on_arrival=on_arrival)
            except ReplayFailed as e:
                _record_failure(
                    e, expected, path, target, out, driver, screens, results, failed_prefixes, log
                )
        report["status"] = "done"
    except (DriverError, KeyboardInterrupt) as e:
        report["status"] = "aborted"
        report["error"] = str(e) or "stopped by user"
        log(f"✘ verify aborted: {report['error']}")
    finally:
        try:
            driver.unpin()
            if anim is not None:
                driver.set_animations(anim)
            if font is not None:
                driver.set_font_scale(font)
        except DriverError:
            pass

    mask_top = cfg.get("diff_mask_top", 0.045)
    for r in results.values():
        if r["status"] != "passed":
            continue
        b = screens[r["screen"]]
        if not b.get("screenshot") or not (base_dir / b["screenshot"]).is_file():
            continue
        cand = {"hierarchy": r["hierarchy"], "width": rp.width, "height": rp.height, "package": pkg}
        text = screen_text_diff(base_dir, b, out, cand, mask_top)
        img = out / "diff" / Path(r["screenshot"]).name
        res = compare_images(
            base_dir / b["screenshot"],
            out / r["screenshot"],
            img,
            mask_top,
            cfg.get("diff_mask_bottom", 0.0),
            marks=[m for m in text["changes"] if not m.get("digits_only")] if text else None,
        )
        r["changed"] = res["changed_ratio"] > CHANGED_ABOVE or text_changed(text)
        r["visual"] = {"diff": f"diff/{img.name}", **res, "text": text}

    order = {"failed": 0, "blocked": 1, "passed": 2, "skipped": 3}
    rows = sorted(results.values(), key=lambda r: (order[r["status"]], not r.get("changed"), r["screen"]))
    report["summary"] = {
        **{k: sum(1 for r in rows if r["status"] == k) for k in order},
        "changed": sum(1 for r in rows if r.get("changed")),
    }
    report["ok"] = report["status"] == "done" and report["summary"]["failed"] == 0
    report["finished_at"] = _now()
    report["screens"] = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    write_json_atomic(out / "verify.json", report)
    report["dir"] = str(out)
    report["_obs"] = {r["screen"]: r["_obs"] for r in rows if "_obs" in r}
    return report


def _record_failure(e, expected, path, target, out, driver, screens, results, failed_prefixes, log) -> None:
    if e.reason == "not_found":
        # The element of step `index` is missing: the screen after it was never reached.
        step_i, failed_i = e.index, e.index + 1
    else:
        step_i, failed_i = e.index - 1, e.index  # step index -1 = the launch itself
    failed = expected[failed_i]
    prefix = tuple((st["screen"], st["key"]) for st in path[: step_i + 1])
    evidence = {}
    safe = target.replace(":", "_")
    try:
        driver.screenshot(out / "failed" / f"{safe}.png")
        evidence["screenshot"] = f"failed/{safe}.png"
    except (DriverError, OSError):
        pass
    if e.obs is not None:
        (out / "failed" / f"{safe}.xml").write_text(e.obs.xml)
        evidence["hierarchy"] = f"failed/{safe}.xml"
    step = path[step_i] if step_i >= 0 else None
    failure = {
        "reason": e.reason,
        "detail": e.detail,
        "step": step_i if step_i >= 0 else None,
        "on": step["screen"] if step else None,
        "action": step["action"] if step else "launch",
        "label": step["label"] if step else None,
        "expected": failed,
        "got": e.got,
        **evidence,
    }
    if failed not in results:
        results[failed] = {
            "screen": failed,
            "title": screens[failed].get("title"),
            "status": "failed",
            "path": expected[:failed_i],
            "failure": failure,
        }
    failed_prefixes[prefix] = failed
    for sid in expected[failed_i + 1 :]:
        results.setdefault(
            sid,
            {
                "screen": sid,
                "title": screens[sid].get("title"),
                "status": "blocked",
                "blocked_by": failed,
                "path": expected[: expected.index(sid)],
            },
        )
    what = "launch" if step is None else f"{step['action']} {step['label']!r} on {step['screen']}"
    log(f"  ✘ {failed}: {e.detail} (after {what})")


def update_baselines(base_dir: str | Path, report: dict) -> list[str]:
    """Accept the new build's look: copy each passed screen's screenshot and hierarchy over the base
    run's, and refresh its tokens and signature in map.json."""
    base_dir = Path(base_dir)
    data = load_map(base_dir)
    out = Path(report["dir"])
    w, h = report["device"]["width"], report["device"]["height"]
    updated = []
    for s in data["screens"]:
        r = next((r for r in report["screens"] if r["screen"] == s["id"] and r["status"] == "passed"), None)
        if r is None or not s.get("screenshot"):
            continue
        png = base_dir / s["screenshot"]
        shutil.copyfile(out / r["screenshot"], png)
        save_thumbnail(png, png.with_suffix(".jpg"))
        xml = (out / r["hierarchy"]).read_text()
        (base_dir / (s.get("hierarchy") or f"screens/{s['id']}.xml")).write_text(xml)
        obs = report["_obs"].get(s["id"]) or analyze(xml, None, s.get("activity"), w, h)
        s["tokens"], s["signature"] = sorted(obs.tokens), obs.signature
        updated.append(s["id"])
    write_json_atomic(base_dir / "map.json", data)
    return updated


def format_verify(rep: dict) -> str:
    s = rep["summary"]
    head = (
        f"{'✔' if rep['ok'] else '✘'} {s['passed']} passed, {s['failed']} failed, {s['blocked']} blocked, "
        f"{s['skipped']} skipped · {s['changed']} visually changed   ({rep['app'].get('version') or '?'} "
        f"vs base {rep['base_app'].get('version') or '?'})"
    )
    lines = [head]
    for r in rep["screens"]:
        if r["status"] == "failed":
            f = r["failure"]
            lines.append(f"  ✘ {r['screen']} {r['title']!r}: {f['detail']}")
            if f.get("screenshot"):
                lines.append(f"      evidence: {Path(rep['dir']) / f['screenshot']}")
        elif r["status"] == "blocked":
            lines.append(f"  ⊘ {r['screen']} {r['title']!r}: blocked by {r['blocked_by']}")
        elif r.get("changed"):
            v = r["visual"]
            t = v.get("text") or {}
            text = ", ".join(f"{t[k]} {k}" for k in ("added", "removed", "moved", "changed") if t.get(k))
            lines.append(
                f"  ≠ {r['screen']} {r['title']!r}: {v['changed_ratio']:.2%} pixels"
                + (f"; text {text}" if text else "")
            )
    lines.append(f"  → {Path(rep['dir']) / 'verify.json'}")
    return "\n".join(lines)
