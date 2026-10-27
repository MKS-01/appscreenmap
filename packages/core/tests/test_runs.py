import json
from pathlib import Path

from appscreenmap.core.notes import run_dir_for
from appscreenmap.core.runs import new_run_dir, resolve_run, update_index


def _fake_run(d: Path, package="dev.example.reader", started="2026-10-13T01:00:00+00:00") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "map.json").write_text(
        json.dumps(
            {
                "run": {"id": d.name, "status": "done", "started_at": started, "app": {"package": package}},
                "screens": [{"id": "s001", "kind": "app", "thumb": "screens/s001.jpg"}],
                "stats": {"screens": 1, "transitions": 0, "crashes": 0},
            }
        )
    )
    return d


def test_new_run_dir_groups_by_project(tmp_path: Path):
    d = new_run_dir(tmp_path, "dev.appscreenmap.playground")
    assert d.parent == tmp_path / "playground" and d.name.startswith("playground-")
    d2 = new_run_dir(tmp_path, "dev.appscreenmap.playground", name="v2 build", project="Playground App")
    assert d2.parent.name == "playground-app" and d2.name.startswith("v2-build-")


def test_index_and_resolution_cover_nested_and_legacy_runs(tmp_path: Path):
    nested = _fake_run(tmp_path / "reader" / "reader-20261013-010000", started="2026-10-13T02:00:00+00:00")
    legacy = _fake_run(tmp_path / "old-20261001-000000", started="2026-10-01T00:00:00+00:00")
    rows = update_index(tmp_path)
    assert [r["id"] for r in rows] == [nested.name, legacy.name]  # newest first
    assert rows[0]["project"] == "reader" and rows[0]["path"] == f"reader/{nested.name}"
    assert rows[0]["thumb"] == f"reader/{nested.name}/screens/s001.jpg"
    assert rows[1]["project"] == "reader" and rows[1]["path"] == legacy.name
    assert json.loads((tmp_path / "index.json").read_text())["runs"] == rows
    assert resolve_run(tmp_path, nested.name) == nested
    assert resolve_run(tmp_path, legacy.name) == legacy
    assert run_dir_for(tmp_path, nested.name) == nested
    for bad in ("missing", "../etc", "reader/x", ""):
        assert resolve_run(tmp_path, bad) is None


def test_index_carries_the_stack_summary_when_a_scan_wrote_one(tmp_path: Path):
    scanned = _fake_run(tmp_path / "reader" / "reader-20261027-010000")
    (scanned / "audits").mkdir()
    (scanned / "audits" / "stack.json").write_text(
        json.dumps(
            {
                "summary": "Flutter",
                "generated_at": "2026-10-27T01:00:00+00:00",
                "facts": {"version": "1.0", "stack": {"kind": "cross-platform"}},
            }
        )
    )
    plain = _fake_run(tmp_path / "other" / "other-20261027-010000", package="dev.example.other")
    rows = {r["id"]: r for r in update_index(tmp_path)}
    assert rows[scanned.name]["stack"] == {
        "kind": "cross-platform",
        "summary": "Flutter",
        "version": "1.0",
        "generated_at": "2026-10-27T01:00:00+00:00",
    }
    assert "stack" not in rows[plain.name]
