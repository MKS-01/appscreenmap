"""Screens added by hand: a screenshot (and optional hierarchy) filed on a canvas when a crawl or recording missed it.

The one write path for `appscreenmap add-screen`, the dashboard endpoint and any agent. A manual screen is a normal
`map.json` screen with `source: "manual"`, no replayable `reach_path`, and, with a parent, one transition. Editing
keeps `map.json`, `titles.json` and `notes.json` in step; refreshing exports and reports is the caller's job
(this package imports nothing else).
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import threading
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

try:
    import fcntl  # a lock shared with other processes (the CLI beside the dashboard); absent on Windows
except ImportError:  # pragma: no cover
    fcntl = None

from . import notes as notes_doc
from .analyzer import analyze
from .media import save_thumbnail
from .model import write_json_atomic

MAX_IMAGE_BYTES = 20_000_000
MAX_PIXELS = 40_000_000  # decoded size, so a tiny PNG can't ask for gigabytes
MAX_HIERARCHY_BYTES = 2_000_000
MAX_TITLE = 200
_APP_ID = re.compile(r"s(\d+)")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


class ManualError(ValueError):
    pass


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


@contextlib.contextmanager
def _locked(run_dir: Path):
    """One writer per canvas at a time: threads of the dashboard server and, through a file lock, other processes."""
    key = str(Path(run_dir).resolve())
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        handle = None
        try:
            if fcntl:
                handle = open(Path(run_dir) / ".manual.lock", "w")  # noqa: SIM115
                fcntl.flock(handle, fcntl.LOCK_EX)
            yield
        finally:
            if handle:
                handle.close()  # closing releases the flock


def _text(raw: object, what: str) -> str | None:
    """An optional text field from a client: a string (control characters turned into spaces) or nothing."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ManualError(f"{what} must be text")
    return " ".join(_CONTROL.sub(" ", raw).split()) or None


def _title(raw: object) -> str:
    title = _text(raw, "title")
    if not title:
        raise ManualError("a screen needs a title")
    return title[:MAX_TITLE]


def _png(image: bytes) -> tuple[bytes, int, int]:
    """The image as PNG bytes with its size; only PNG and JPEG are taken."""
    if not isinstance(image, (bytes, bytearray)) or not image or len(image) > MAX_IMAGE_BYTES:
        raise ManualError("image missing or over 20 MB")
    try:
        with Image.open(io.BytesIO(image)) as im:
            if im.format not in ("PNG", "JPEG"):
                raise ManualError("image must be PNG or JPEG")
            if im.width * im.height > MAX_PIXELS:
                raise ManualError("image is too large")
            if im.format == "PNG":
                return bytes(image), im.width, im.height
            out = io.BytesIO()
            im.convert("RGB").save(out, "PNG")
            return out.getvalue(), im.width, im.height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ManualError("image must be PNG or JPEG, at a sane size") from e


def _find(data: dict, sid: str) -> dict:
    for s in data["screens"]:
        if s["id"] == sid:
            return s
    raise ManualError(f"no screen {sid}")


def _parent_row(data: dict, parent: str | None) -> dict | None:
    row = _find(data, parent) if parent else None
    if row and row["kind"] != "app":
        raise ManualError("the parent must be an app screen")
    return row


def _scenario_of(data: dict, parent: dict | None, scenario: str | None) -> str | None:
    scenarios = data["run"].get("scenarios") or []
    if scenario:
        if scenario not in {s["id"] for s in scenarios}:
            raise ManualError(f"no scenario {scenario}")
        return scenario
    if parent and parent.get("scenario"):
        return parent["scenario"]
    return scenarios[-1]["id"] if scenarios else None


def _new_scenario(data: dict, label: str) -> str:
    """A scenario for a tree of its own (e.g. onboarding); an existing one with the same label is reused."""
    scenarios = data["run"].setdefault("scenarios", [])
    for sc in scenarios:
        if sc.get("label") == label:
            return sc["id"]
    nums = [int(m.group(1)) for sc in scenarios if (m := re.fullmatch(r"sc(\d+)", sc["id"]))]
    sid = f"sc{max(nums, default=0) + 1}"
    now = _now()
    scenarios.append(
        {"id": sid, "label": label, "run_id": None, "started_at": now, "finished_at": now, "steps": 0,
         "screens": [], "entry": [], "playbook": None, "source": "manual"}
    )  # fmt: skip
    return sid


def _would_loop(data: dict, sid: str, parent: str) -> bool:
    """True when `parent` already hangs under `sid` (any link, crawled or manual), so moving `sid` there makes a loop."""
    up: dict[str, list[str]] = {}
    for t in data["transitions"]:
        if t["from"] != t["to"]:
            up.setdefault(t["to"], []).append(t["from"])
    seen, stack = set(), [parent]
    while stack:
        cur = stack.pop()
        if cur == sid:
            return True
        if cur not in seen:
            seen.add(cur)
            stack.extend(up.get(cur, []))
    return False


def _link(data: dict, parent: dict, child: dict, via: str) -> None:
    n = 1 + max((int(t["id"][1:]) for t in data["transitions"] if re.fullmatch(r"t\d+", t["id"])), default=0)
    data["transitions"].append(
        {
            "id": f"t{n}",
            "from": parent["id"],
            "to": child["id"],
            "key": f"manual|{via}",
            "action": "click",
            "label": via,
            "kind": "button",
            "count": 0,
            "step": 0,
            "inferred": False,
            "load_ms": None,
            "timings": [],
            "source": "manual",
            **({"scenario": child["scenario"]} if child.get("scenario") else {}),
        }
    )


def _refresh_stats(data: dict) -> None:
    app = [s for s in data["screens"] if s["kind"] == "app"]
    st = data.setdefault("stats", {})
    st.update(screens=len(app), transitions=len(data["transitions"]))
    scenarios = data["run"].get("scenarios")
    if scenarios:
        for sc in scenarios:
            sc["screens"] = [s["id"] for s in app if s.get("scenario") == sc["id"]]


def _set_title_files(run_dir: Path, sid: str, title: str) -> None:
    """titles.json (display titles) and the viewer's rename override follow the new title when they hold one."""
    p = run_dir / "titles.json"
    if p.is_file():
        doc = json.loads(p.read_text())
        if isinstance(doc.get("titles"), dict):
            doc["titles"][sid] = title
            write_json_atomic(p, doc)
    if (run_dir / notes_doc.NOTES_FILE).is_file():
        notes = notes_doc.load(run_dir)
        if sid in notes["edits"]["titles"]:
            notes["edits"]["titles"][sid] = title
            write_json_atomic(run_dir / notes_doc.NOTES_FILE, notes)


def _mentioned_ids(run_dir: Path) -> set[str]:
    p = run_dir / notes_doc.NOTES_FILE
    if not p.is_file():
        return set()
    n = notes_doc.load(run_dir)
    e = n["edits"]
    return {*e["deleted"], *e["parents"], *e["titles"], *e["labels"], *n["notes"]}


def _place_in_tree(run_dir: Path, sid: str, parent: str | None, via: str) -> None:
    """The viewer's tree parents a screen by its reach path, which a manual screen does not have: say where it hangs
    in notes.json (`edits.parents`, `edits.labels`), the same place a screen moved in the viewer is kept."""
    notes = notes_doc.load(run_dir)
    notes["edits"]["deleted"] = [
        d for d in notes["edits"]["deleted"] if d != sid
    ]  # filing it again un-hides it
    notes["edits"]["parents"][sid] = parent
    notes["edits"]["labels"][sid] = via
    notes["run"] = run_dir.name
    write_json_atomic(run_dir / notes_doc.NOTES_FILE, notes)


def _analyse(hierarchy: object, pkg: str | None, width: int, height: int):
    if not isinstance(hierarchy, str):
        raise ManualError("hierarchy must be text")
    if len(hierarchy.encode()) > MAX_HIERARCHY_BYTES:
        raise ManualError("hierarchy over 2 MB")
    try:
        return analyze(hierarchy, pkg, None, width, height)
    except Exception as e:  # malformed XML of any kind
        raise ManualError(f"hierarchy is not a uiautomator dump: {e}") from e


def add_screen(
    run_dir: Path,
    image: bytes,
    title: str,
    *,
    parent: str | None = None,
    via: str | None = None,
    scenario: str | None = None,
    new_scenario: str | None = None,
    hierarchy: str | None = None,
) -> dict:
    """File one screen on the canvas and return its `map.json` row. Raises ManualError before writing anything."""
    run_dir = Path(run_dir)
    with _locked(run_dir):
        return _add(run_dir, image, title, parent, via, scenario, new_scenario, hierarchy)


def _add(run_dir, image, title, parent, via, scenario, new_scenario, hierarchy) -> dict:
    data = json.loads((run_dir / "map.json").read_text())
    title = _title(title)
    parent, via = _text(parent, "parent"), _text(via, "via")
    scenario, new_scenario = _text(scenario, "scenario"), _text(new_scenario, "new scenario")
    png, width, height = _png(image)
    parent_row = _parent_row(data, parent)
    if via and not parent_row:
        raise ManualError("--via needs a parent")
    if new_scenario and (scenario or parent_row):
        raise ManualError("a new scenario starts a tree: give it no parent and no scenario")
    sc = _new_scenario(data, new_scenario) if new_scenario else _scenario_of(data, parent_row, scenario)
    pkg = data["run"].get("app", {}).get("package")
    obs = _analyse(hierarchy, pkg, width, height) if hierarchy else None

    # Ids the viewer's notes still mention (a tree edit on a screen that no longer exists) are never reused: the new
    # screen would inherit that edit, a stale "deleted" included.
    mentioned = _mentioned_ids(run_dir)
    nums = [
        int(m.group(1))
        for i in [*(s["id"] for s in data["screens"]), *mentioned]
        if (m := _APP_ID.fullmatch(i))
    ]
    sid = f"s{max(nums, default=0) + 1:03d}"
    shots = run_dir / "screens"
    shots.mkdir(exist_ok=True)
    (shots / f"{sid}.png").write_bytes(png)
    save_thumbnail(shots / f"{sid}.png", shots / f"{sid}.jpg")
    if hierarchy:
        (shots / f"{sid}.xml").write_text(hierarchy, encoding="utf-8")

    row = {
        "id": sid,
        "kind": "app",
        "title": title,
        "activity": None,
        "package": pkg,
        "signature": obs.signature if obs else f"manual-{sid}",
        "patterns": obs.patterns if obs else [],
        "depth": (parent_row.get("depth") or 0) + 1 if parent_row else 0,
        "visits": 0,
        "first_step": 1
        + max(
            (x.get("first_step") or 0 for x in data["screens"]), default=0
        ),  # the viewer orders trees by it: after what is already there
        "width": width,
        "height": height,
        "screenshot": f"screens/{sid}.png",
        "thumb": f"screens/{sid}.jpg",
        "hierarchy": f"screens/{sid}.xml" if hierarchy else None,
        "captures": {},
        "variant_of": None,
        "origin": "unknown",  # no replayable path: no Maestro flow and no `route` steps until a crawl reaches it
        "reach_path": [],
        "autofill": [],
        "tokens": sorted(obs.tokens) if obs else [],
        "elements": [],
        "source": "manual",
        "added_at": _now(),
    }
    if sc:
        row["scenario"] = sc
    data["screens"].append(row)
    if new_scenario:
        next(c for c in data["run"]["scenarios"] if c["id"] == sc)["entry"].append(sid)
    label = via or title
    if parent_row:
        _link(data, parent_row, row, label)
    _refresh_stats(data)
    write_json_atomic(run_dir / "map.json", data)
    _set_title_files(run_dir, sid, title)
    if parent_row:
        _place_in_tree(run_dir, sid, parent_row["id"], label)
    elif new_scenario:
        _place_in_tree(run_dir, sid, None, title)  # a root of its own
    return row


def update_screen(
    run_dir: Path,
    sid: str,
    *,
    title: str | None = None,
    parent: str | None = None,
    via: str | None = None,
    scenario: str | None = None,
    image: bytes | None = None,
    hierarchy: str | None = None,
    captures: dict[str, bytes] | None = None,
) -> dict:
    """Edit a manual screen's title, parent link (and its label), scenario, screenshot, hierarchy or extra captures
    (`captures`: name -> image, e.g. "bottom" for the scrolled-down view); crawled screens never. Everything is
    checked before the first file is written, so a refused edit changes nothing."""
    run_dir = Path(run_dir)
    with _locked(run_dir):
        return _update(run_dir, sid, title, parent, via, scenario, image, hierarchy, captures)


def _update(run_dir, sid, title, parent, via, scenario, image, hierarchy, captures) -> dict:
    data = json.loads((run_dir / "map.json").read_text())
    row = _find(data, sid)
    if row.get("source") != "manual":
        raise ManualError(f"{sid} was crawled; only manual screens can be edited")

    # ── check everything first ──
    new_title = _title(title) if title is not None else None
    parent, via, scenario = _text(parent, "parent"), _text(via, "via"), _text(scenario, "scenario")
    new_png = _png(image) if image is not None else None
    width, height = (new_png[1], new_png[2]) if new_png else (row["width"], row["height"])
    obs = None
    if hierarchy is not None:
        obs = _analyse(hierarchy, data["run"].get("app", {}).get("package"), width, height)
    if captures is not None and not isinstance(captures, dict):
        raise ManualError("captures must be a name -> image map")
    shots = {}
    for name, img in (captures or {}).items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_-]{1,32}", name):
            raise ManualError("capture names are lowercase letters, digits, - and _")
        shots[name] = _png(img)[0]
    new_scenario = _scenario_of(data, None, scenario) if scenario else None
    mine = [t for t in data["transitions"] if t["to"] == sid and t.get("source") == "manual"]
    relink = None
    if parent is not None or via is not None:
        if parent is None and mine:
            parent = mine[0]["from"]
        if parent is None:
            raise ManualError("--via needs a parent")
        if parent == sid or _would_loop(data, sid, parent):
            raise ManualError("a screen cannot go under itself or one of its own children")
        parent_row = _parent_row(data, parent)
        relink = (parent_row, via or (mine[0]["label"] if mine else new_title or row["title"]))

    # ── then write ──
    if new_title is not None:
        row["title"] = new_title
    if new_png:
        row["width"], row["height"] = width, height
        (run_dir / row["screenshot"]).write_bytes(new_png[0])
        save_thumbnail(run_dir / row["screenshot"], run_dir / row["thumb"])
    if obs:
        (run_dir / "screens").mkdir(exist_ok=True)
        (run_dir / "screens" / f"{sid}.xml").write_text(hierarchy, encoding="utf-8")
        row.update(
            hierarchy=f"screens/{sid}.xml",
            patterns=obs.patterns,
            tokens=sorted(obs.tokens),
            signature=obs.signature,
        )
    for name, png in shots.items():
        (run_dir / "screens").mkdir(exist_ok=True)
        (run_dir / "screens" / f"{sid}-{name}.png").write_bytes(png)
        row.setdefault("captures", {})[name] = f"screens/{sid}-{name}.png"
    if new_scenario:
        row["scenario"] = new_scenario
        for t in mine:
            t["scenario"] = new_scenario
    placed = None
    if relink:
        parent_row, label = relink
        data["transitions"] = [t for t in data["transitions"] if t not in mine]
        _link(data, parent_row, row, label)
        row["depth"] = (parent_row.get("depth") or 0) + 1
        placed = (parent_row["id"], label)
    _refresh_stats(data)
    write_json_atomic(run_dir / "map.json", data)
    if new_title is not None:
        _set_title_files(run_dir, sid, row["title"])
    if placed:
        _place_in_tree(run_dir, sid, *placed)
    return row
