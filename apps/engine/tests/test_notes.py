import json

import pytest

from appscreenmap import notes


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "app-20261013-000000"
    d.mkdir()
    (d / "map.json").write_text("{}")
    return d


def test_save_and_load_roundtrip(run_dir):
    doc = {
        "appscreenmap_notes": 1,
        "run": "spoofed",
        "notes": {
            "s001": {"star": True, "note": "home", "updated": "2026-10-13T00:00:00Z"},
            "s002": {"star": False, "note": "  ", "updated": "x"},  # empty → dropped
        },
    }
    notes.save(run_dir, json.dumps(doc).encode())
    loaded = notes.load(run_dir)
    assert loaded["run"] == run_dir.name
    assert loaded["notes"] == {"s001": {"star": True, "note": "home", "updated": "2026-10-13T00:00:00Z"}}


def test_load_missing_file_is_empty(run_dir):
    assert notes.load(run_dir)["notes"] == {}


@pytest.mark.parametrize("raw", [b"{oops", b'{"notes": {}}', b'{"appscreenmap_notes": 1, "notes": []}'])
def test_save_rejects_bad_documents(run_dir, raw):
    with pytest.raises(notes.NotesError):
        notes.save(run_dir, raw)
    assert not (run_dir / notes.NOTES_FILE).exists()


def test_save_rejects_oversized(run_dir):
    with pytest.raises(notes.NotesError):
        notes.save(run_dir, b" " * (notes.MAX_BYTES + 1))


@pytest.mark.parametrize("run_id", ["..", "../etc", "a/b", "", ".hidden", "missing-run"])
def test_run_dir_for_rejects_unsafe_or_unknown(tmp_path, run_dir, run_id):
    assert notes.run_dir_for(tmp_path, run_id) is None


def test_run_dir_for_accepts_existing_run(tmp_path, run_dir):
    assert notes.run_dir_for(tmp_path, run_dir.name) == run_dir


def test_a11y_triage_roundtrip(run_dir):
    doc = {
        "appscreenmap_notes": 1,
        "notes": {},
        "a11y": {
            "s001::touch-target::id/fab::Add::900,2000": {
                "status": "wontfix",
                "note": "design",
                "updated": "t",
            }
        },
    }
    notes.save(run_dir, json.dumps(doc).encode())
    assert notes.load(run_dir)["a11y"] == {
        "s001::touch-target::id/fab::Add::900,2000": {"status": "wontfix", "note": "design", "updated": "t"}
    }


@pytest.mark.parametrize("a11y", [[], {"k": {"status": "maybe"}}, {"k": "confirmed"}])
def test_a11y_triage_rejects_bad_values(run_dir, a11y):
    doc = {"appscreenmap_notes": 1, "notes": {}, "a11y": a11y}
    with pytest.raises(notes.NotesError):
        notes.save(run_dir, json.dumps(doc).encode())
