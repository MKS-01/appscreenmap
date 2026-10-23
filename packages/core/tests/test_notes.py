import json

import pytest

from appscreenmap.core import notes


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


def test_comments_and_edits_are_validated_and_kept():
    doc = {
        "appscreenmap_notes": 1,
        "notes": {},
        "comments": {
            "c1": {
                "id": "c1",
                "x": 10,
                "y": 20,
                "screen": "s003",
                "tag": "bug",
                "text": "Wrong title",
                "replies": [{"text": "fixed in v2", "created": "2026-10-16"}, {"text": " "}],
            },
            "c2": {"id": "c2", "x": 1, "y": 2, "tag": "nope", "status": "weird", "text": "Loose pin"},
        },
        "edits": {
            "titles": {"s002": "Privacy sheet", "s003": " "},
            "deleted": ["s009", "s009"],
            "parents": {"s005": None, "s006": "s001"},
            "added": {"n-1": {"title": "Forgot password", "parent": "s003", "created": "2026-10-16"}},
            "labels": {"s004": "Sign in", "s005": ""},
        },
    }
    out = notes.validate(doc)
    assert out["comments"]["c1"]["screen"] == "s003" and len(out["comments"]["c1"]["replies"]) == 1
    assert (out["comments"]["c2"]["tag"], out["comments"]["c2"]["status"]) == ("flow", "open")
    assert "screen" not in out["comments"]["c2"]
    assert out["edits"] == {
        "titles": {"s002": "Privacy sheet"},
        "deleted": ["s009"],
        "parents": {"s005": None, "s006": "s001"},
        "added": {"n-1": {"title": "Forgot password", "parent": "s003", "created": "2026-10-16"}},
        "labels": {"s004": "Sign in"},
    }


def test_a_planned_screen_needs_a_title():
    base = {"appscreenmap_notes": 1, "notes": {}}
    with pytest.raises(notes.NotesError, match="no title"):
        notes.validate({**base, "edits": {"added": {"n-1": {"title": " ", "parent": None}}}})
    with pytest.raises(notes.NotesError, match="bad parent"):
        notes.validate({**base, "edits": {"added": {"n-1": {"title": "x", "parent": 3}}}})


def test_a_comment_needs_text_and_numbers():
    base = {"appscreenmap_notes": 1, "notes": {}}
    with pytest.raises(notes.NotesError, match="no text"):
        notes.validate({**base, "comments": {"c": {"x": 1, "y": 1, "text": " "}}})
    with pytest.raises(notes.NotesError, match="number"):
        notes.validate({**base, "comments": {"c": {"x": "1", "y": 1, "text": "hi"}}})


def test_stickies_roundtrip_and_clean(run_dir):
    doc = {
        "appscreenmap_notes": 1,
        "notes": {},
        "stickies": {
            "k1": {"x": 10, "y": 20, "screen": "s002", "text": "Check the empty state"},
            "k2": {
                "x": 1,
                "y": 2,
                "color": "neon",
                "text": "",
            },  # unknown colour → yellow; empty text kept (a fresh note)
        },
    }
    notes.save(run_dir, json.dumps(doc).encode())
    s = notes.load(run_dir)["stickies"]
    assert s["k1"]["screen"] == "s002"
    assert "screen" not in s["k2"] and "color" not in s["k2"]


def test_old_notes_file_has_no_stickies(run_dir):
    notes.save(run_dir, b'{"appscreenmap_notes": 1, "notes": {}}')
    assert notes.load(run_dir)["stickies"] == {}


def test_save_rejects_bad_sticky(run_dir):
    with pytest.raises(notes.NotesError):
        notes.save(
            run_dir, b'{"appscreenmap_notes": 1, "notes": {}, "stickies": {"k": {"x": "a", "text": "t"}}}'
        )


def test_layout_and_tree_order_roundtrip_and_default(run_dir):
    assert notes.load(run_dir)["layout"] == {} and notes.load(run_dir)["tree_order"] == []
    doc = {
        "appscreenmap_notes": 1,
        "notes": {},
        "layout": {"s001": {"x": 12, "y": -3.5}},
        "tree_order": ["s020", "s001", "s020"],  # a repeat is dropped, order kept
    }
    notes.save(run_dir, json.dumps(doc).encode())
    loaded = notes.load(run_dir)
    assert loaded["layout"] == {"s001": {"x": 12.0, "y": -3.5}} and loaded["tree_order"] == ["s020", "s001"]


@pytest.mark.parametrize(
    "bad",
    [
        {"layout": []},
        {"layout": {"s001": {"x": "1", "y": 2}}},
        {"layout": {"s001": {"x": 1}}},
        {"layout": {"s001": {"x": 1e9, "y": 0}}},
        {"layout": {"s001": {"x": float("nan"), "y": 0}}},
        {"layout": {"": {"x": 1, "y": 0}}},
        {"layout": {f"s{i}": {"x": 0, "y": 0} for i in range(notes.MAX_LAYOUT + 1)}},
        {"tree_order": "s001"},
        {"tree_order": [1]},
        {"tree_order": [f"s{i}" for i in range(notes.MAX_TREE_ORDER + 1)]},
    ],
)
def test_bad_layout_or_tree_order_is_refused(bad):
    with pytest.raises(notes.NotesError):
        notes.validate({"appscreenmap_notes": 1, "notes": {}, **bad})
