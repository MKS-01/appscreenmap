from __future__ import annotations

from pathlib import Path

from PIL import Image

from appscreenmap.regression.visual import compare_images


def test_compare_images_detects_change(tmp_path: Path):
    a, b, c = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    Image.new("RGB", (100, 200), "white").save(a)
    img = Image.new("RGB", (100, 200), "white")
    img.paste((0, 0, 0), (40, 100, 60, 120))
    img.save(b)
    res = compare_images(a, b, tmp_path / "d.png", mask_top=0.05, mask_bottom=0)
    assert res["changed_ratio"] > 0 and res["bbox"] == [40, 100, 60, 120]
    Image.new("RGB", (100, 200), "white").save(c)
    assert compare_images(a, c, tmp_path / "e.png", 0.05, 0)["changed_ratio"] == 0
