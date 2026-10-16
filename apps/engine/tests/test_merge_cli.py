"""`merge --into <canvas> <run> --move`: a re-run joins the app's one canvas in place, keeps what people added in the
viewer, and leaves no separate run behind."""

from __future__ import annotations

import json

from appscreenmap.engine.cli import main
from appscreenmap.testkit.fakedevice import FakeDriver, crawl


def test_a_rerun_moves_into_the_canvas_and_keeps_its_notes(tmp_path):
    canvas, _ = crawl(tmp_path, FakeDriver(), run_id="canvas")
    rerun, _ = crawl(tmp_path, FakeDriver(), run_id="proj-20261016-120000")
    (canvas / "notes.json").write_text(
        json.dumps(
            {
                "appscreenmap_notes": 1,
                "notes": {},
                "comments": {"c1": {"x": 1, "y": 2, "screen": "s001", "tag": "bug", "text": "Keep me"}},
                "edits": {"added": {"n-1": {"title": "Planned", "parent": "s001"}}},
            }
        )
    )
    before = len(json.loads((canvas / "map.json").read_text())["screens"])

    args = [
        "merge",
        "--into",
        str(canvas),
        str(rerun),
        "--labels",
        "Re-run",
        "--move",
        "--out",
        str(tmp_path),
    ]
    assert main(args) == 0

    m = json.loads((canvas / "map.json").read_text())
    assert m["run"]["id"] == "canvas" and [sc["label"] for sc in m["run"]["scenarios"]][-1] == "Re-run"
    assert len(m["screens"]) > before
    doc = json.loads((canvas / "notes.json").read_text())
    assert doc["comments"]["c1"]["screen"] == "s001" and doc["edits"]["added"]["n-1"]["parent"] == "s001"
    assert not rerun.exists()  # one canvas per app: the re-run lives only in the canvas now
