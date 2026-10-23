"""Merge several runs of one app into a single canvas, one scenario per source run.

Screens are renumbered so ids stay unique; every screen and transition carries the `scenario` it came from, and each
scenario keeps its own entry screen(s) (origin "launch"), so the viewer draws one tree per scenario side by side.
External screens (`x:<package>`) are shared. What people added in the viewer (notes.json: stars, notes, a11y decisions,
map comments, tree edits) and titles.json follow their screens under the new ids, and so do captured rows
(network.jsonl, logs.jsonl, manual sessions/). Derived files (a11y, perf, flows) are rebuilt from the merged map by
the caller.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import notes as notes_doc
from .model import SCHEMA_VERSION, write_json_atomic

STAMP_RE = re.compile(r"-\d{8}-\d{6}$")


def default_label(run_dir: Path) -> str:
    return STAMP_RE.sub("", run_dir.name)


def _max_step(m: dict) -> int:
    steps = [s.get("first_step") or 0 for s in m["screens"]]
    steps += [t.get("step") or 0 for t in m["transitions"]]
    steps += [e.get("step") or 0 for e in m["events"]]
    return max(steps, default=0)


def _rename_paths(value, old: str, new: str):
    """Rewrite `screens/<old>.ext` / `screens/<old>-name.ext` strings to the new id, in nested dicts and strings."""
    pat = re.compile(rf"(?<=screens/){re.escape(old)}(?=[.\-])")
    if isinstance(value, str):
        return pat.sub(new, value)
    if isinstance(value, dict):
        return {k: _rename_paths(v, old, new) for k, v in value.items()}
    return value


def _remap(steps, idmap: dict[str, str]) -> list[dict]:
    return [{**st, "screen": idmap.get(st["screen"], st["screen"])} for st in steps or []]


def _scenario(item: dict, sc_map: dict) -> str:
    """The new scenario id of a screen, transition or event; a plain run has one scenario, whatever the item says."""
    return sc_map.get(item.get("scenario")) or next(iter(sc_map.values()))


def merge_runs(run_dirs: list[Path], out_dir: Path, name: str, labels: list[str] | None = None) -> dict:
    """Write the merged run into `out_dir` (an empty, existing folder). Returns the merged map.json data."""
    maps = [json.loads((d / "map.json").read_text()) for d in run_dirs]
    labels = labels or [default_label(d) for d in run_dirs]
    if len(labels) != len(run_dirs):
        raise ValueError("one label per run")
    packages = {m["run"].get("app", {}).get("package") for m in maps}
    if len(packages) != 1:
        raise ValueError(f"runs are of different apps: {sorted(map(str, packages))}")
    (out_dir / "screens").mkdir(parents=True, exist_ok=True)

    screens: list[dict] = []
    transitions: list[dict] = []
    events: list[dict] = []
    scenarios: list[dict] = []
    externals: dict[str, dict] = {}
    idmaps: list[dict[str, str]] = []
    sc_maps: list[dict] = []
    offsets: list[int] = []
    offset = 0
    for i, (d, m, label) in enumerate(zip(run_dirs, maps, labels, strict=True)):
        # A source that is already a canvas keeps its scenarios; a plain run is one scenario named by `label`.
        parts = m["run"].get("scenarios") or [
            {
                "id": None,
                "label": label,
                "run_id": m["run"].get("id") or d.name,
                "started_at": m["run"].get("started_at"),
                "finished_at": m["run"].get("finished_at"),
                "steps": m["run"].get("steps"),
                "playbook": m["run"].get("playbook"),
                "network": m["run"].get("network"),
                "logs": m["run"].get("logs"),
            }
        ]
        sc_map = {p["id"]: f"sc{len(scenarios) + k + 1}" for k, p in enumerate(parts)}
        sc_maps.append(sc_map)
        offsets.append(offset)

        idmap: dict[str, str] = {}
        idmaps.append(idmap)
        rows: list[dict] = []
        for s in m["screens"]:
            old = s["id"]
            first = (s.get("first_step") or 0) + offset
            if old.startswith("x:"):  # external screens are shared by every scenario
                idmap[old] = old
                externals.setdefault(old, {**s, "scenario": _scenario(s, sc_map), "first_step": first})
                continue
            new = f"s{len(screens) + len(rows) + 1:03d}"
            idmap[old] = new
            row = {
                **s,
                **_rename_paths(
                    {k: s[k] for k in ("screenshot", "thumb", "hierarchy", "captures") if k in s}, old, new
                ),
            }
            row.update(id=new, scenario=_scenario(s, sc_map), first_step=first)
            rows.append(row)
            for f in sorted((d / "screens").glob(f"{old}[.-]*")):
                shutil.copy2(f, out_dir / "screens" / (new + f.name[len(old) :]))

        for row in rows:
            row["variant_of"] = idmap.get(row["variant_of"]) if row.get("variant_of") else None
            row["reach_path"] = _remap(row.get("reach_path"), idmap)
            for e in row["elements"]:
                if e.get("target"):
                    e["target"] = idmap.get(e["target"], e["target"])
                if e.get("revealed_by"):
                    e["revealed_by"] = _remap(e["revealed_by"], idmap)
        screens += rows
        for t in m["transitions"]:
            t = {**t, "from": idmap[t["from"]], "to": idmap[t["to"]], "step": (t.get("step") or 0) + offset}
            transitions.append({**t, "scenario": _scenario(t, sc_map)})
        events += [
            {**e, "step": (e.get("step") or 0) + offset, "scenario": _scenario(e, sc_map)}
            for e in m["events"]
        ]
        for part in parts:
            mine = [r for r in rows if r["scenario"] == sc_map[part["id"]]]
            scenarios.append(
                {
                    "id": sc_map[part["id"]],
                    "label": part["label"],
                    "run_id": part.get("run_id"),
                    "started_at": part.get("started_at"),
                    "finished_at": part.get("finished_at"),
                    "steps": part.get("steps"),
                    "screens": [r["id"] for r in mine],
                    "entry": [r["id"] for r in mine if r.get("origin") == "launch"],
                    "playbook": part.get("playbook"),
                    **{k: part[k] for k in ("network", "logs") if part.get(k)},
                }
            )
        # run.steps too: a run that ends on same-screen steps has capture rows past its last transition.
        offset += max(_max_step(m), m["run"].get("steps") or 0)

    screens += list(externals.values())
    for n, t in enumerate(transitions, 1):
        t["id"] = f"t{n}"

    base = maps[-1]["run"]
    run = {k: v for k, v in base.items() if k not in ("playbook", "network", "logs")}  # per scenario instead
    run.update(
        id=name,
        status="done",
        started_at=min((s["started_at"] for s in scenarios if s["started_at"]), default=None),
        finished_at=max(
            (s["finished_at"] for s in scenarios if s["finished_at"]), default=None
        ),  # None: interrupted
        steps=sum(s["steps"] or 0 for s in scenarios),
        elapsed_s=round(sum(m["run"].get("elapsed_s") or 0 for m in maps), 1),
        scenarios=scenarios,
        merged_from=[s["run_id"] for s in scenarios],
    )
    app_screens = [s for s in screens if s["kind"] == "app"]
    declared = set(run.get("app", {}).get("activities") or [])
    visited = {s["activity"] for s in app_screens if s.get("activity")}
    statuses: dict[str, int] = {}
    for s in app_screens:
        for e in s["elements"]:
            statuses[e["status"]] = statuses.get(e["status"], 0) + 1
    data = {
        "schema": SCHEMA_VERSION,
        "run": run,
        "screens": screens,
        "transitions": transitions,
        "events": events,
        "perf": maps[0].get("perf", {}),
        "stats": {
            "screens": len(app_screens),
            "external": len(screens) - len(app_screens),
            "transitions": len(transitions),
            "max_depth": max((s["depth"] for s in app_screens), default=0),
            "activities_visited": sorted(visited),
            "activities_declared": len(declared),
            "activity_coverage": round(len(visited & declared) / len(declared), 3) if declared else None,
            "crashes": len([e for e in events if e["type"] == "crash"]),
            "elements": statuses,
        },
    }
    write_json_atomic(out_dir / "map.json", data)
    _carry_notes(run_dirs, idmaps, out_dir)
    _carry_titles(run_dirs, idmaps, out_dir)
    _carry_captures(run_dirs, idmaps, sc_maps, offsets, out_dir)
    return data


# The timeline ties network and log rows to screens; the trace is Crawl replay's steps.
CAPTURES = ("network.jsonl", "logs.jsonl", "timeline.jsonl", "trace.jsonl")


def _remap_rows(text: str, idmap: dict[str, str], sc_map: dict | None, offset: int = 0) -> str:
    out = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        for key in ("screen", "to"):  # `to`: where a trace step led
            if row.get(key):
                row[key] = idmap.get(row[key], row[key])
        if offset and isinstance(row.get("step"), int):  # a playbook trace row's `step` is its description
            row["step"] += offset
        if sc_map is not None:
            row["scenario"] = _scenario(row, sc_map)
        out.append(json.dumps(row, ensure_ascii=False) + "\n")
    return "".join(out)


def _carry_captures(
    run_dirs: list[Path], idmaps: list[dict[str, str]], sc_maps: list[dict], offsets: list[int], out_dir: Path
) -> None:
    """Each run's network and log rows (tagged with their scenario) and its manual sessions, under the new screen ids."""
    for name in CAPTURES:
        parts = [
            _remap_rows((d / name).read_text(encoding="utf-8", errors="replace"), idmap, sc_map, offset)
            for d, idmap, sc_map, offset in zip(run_dirs, idmaps, sc_maps, offsets, strict=True)
            if (d / name).is_file()
        ]
        if parts or name == "trace.jsonl":  # Crawl replay reads the trace, so the canvas always has one
            (out_dir / name).write_text("".join(parts), encoding="utf-8")
    for d, idmap in zip(run_dirs, idmaps, strict=True):
        for sess in sorted((d / "sessions").glob("*/")) if (d / "sessions").is_dir() else []:
            dest = out_dir / "sessions" / sess.name
            shutil.copytree(sess, dest, dirs_exist_ok=True)
            for f in dest.glob("*.jsonl"):
                f.write_text(_remap_rows(f.read_text(encoding="utf-8", errors="replace"), idmap, None))
            if doc := _read(dest / "session.json"):
                doc["screens"] = sorted({idmap.get(s, s) for s in doc.get("screens") or []})
                (dest / "session.json").write_text(json.dumps(doc, indent=1) + "\n")


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text()) if path.is_file() else None
    except (OSError, ValueError):
        return None


def _carry_notes(run_dirs: list[Path], idmaps: list[dict[str, str]], out_dir: Path) -> None:
    """notes.json of every source, its screen ids rewritten (planned screens, ids "n-…", keep theirs)."""
    out = notes_doc.load(out_dir)
    found = False
    for d, idmap in zip(run_dirs, idmaps, strict=True):
        raw = _read(d / notes_doc.NOTES_FILE)
        try:
            doc = notes_doc.validate(raw) if raw is not None else None
        except notes_doc.NotesError:
            doc = None
        if doc is None:
            continue
        found = True

        def sid(x, idmap=idmap):
            return idmap.get(x, x) if isinstance(x, str) else x

        out["notes"].update({sid(k): v for k, v in doc["notes"].items()})
        for key, t in doc["a11y"].items():  # keys are "<screen id>::<rule>::…"
            head, sep, rest = key.partition("::")
            out["a11y"][sid(head) + sep + rest] = t
        for cid, c in doc["comments"].items():
            out["comments"][cid] = {**c, "screen": sid(c["screen"])} if "screen" in c else c
        for nid, n in doc["stickies"].items():
            out["stickies"][nid] = {**n, "screen": sid(n["screen"])} if "screen" in n else n
        e, o = doc["edits"], out["edits"]
        o["titles"].update({sid(k): v for k, v in e["titles"].items()})
        o["deleted"] = sorted({*o["deleted"], *map(sid, e["deleted"])})
        o["parents"].update({sid(k): sid(v) for k, v in e["parents"].items()})
        o["added"].update({k: {**a, "parent": sid(a["parent"])} for k, a in e["added"].items()})
        o["labels"].update({sid(k): v for k, v in e["labels"].items()})
        out["layout"].update({sid(k): v for k, v in doc["layout"].items()})
        out["layout"] = dict(
            list(out["layout"].items())[-notes_doc.MAX_LAYOUT :]
        )  # the merged file must still load
        out["tree_order"] = list(dict.fromkeys([*out["tree_order"], *map(sid, doc["tree_order"])]))[
            : notes_doc.MAX_TREE_ORDER
        ]
    if found:
        out["run"] = out_dir.name
        write_json_atomic(out_dir / notes_doc.NOTES_FILE, out)


def _carry_titles(run_dirs: list[Path], idmaps: list[dict[str, str]], out_dir: Path) -> None:
    """titles.json (display titles, e.g. English for a run crawled in another language) under the new ids."""
    language, titles = None, {}
    for d, idmap in zip(run_dirs, idmaps, strict=True):
        doc = _read(d / "titles.json")
        if not isinstance(doc, dict) or not isinstance(doc.get("titles"), dict):
            continue
        language = language or doc.get("language")
        titles.update({idmap.get(k, k): v for k, v in doc["titles"].items() if isinstance(v, str)})
    if titles:
        write_json_atomic(out_dir / "titles.json", {"language": language, "titles": titles})
