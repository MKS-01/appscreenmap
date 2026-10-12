import json
from pathlib import Path

from appscreenmap.notes import run_dir_for
from appscreenmap.runs import new_run_dir, resolve_run, update_index


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
    d = new_run_dir(tmp_path, "dev.mks.sample-app")
    assert d.parent == tmp_path / "sample-app" and d.name.startswith("sample-app-")
    d2 = new_run_dir(tmp_path, "dev.mks.sample-app", name="v2 build", project="sample-app App")
    assert d2.parent.name == "sample-app-app" and d2.name.startswith("v2-build-")


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
