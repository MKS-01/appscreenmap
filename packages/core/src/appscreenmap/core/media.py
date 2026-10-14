"""Image helpers: thumbnails for the viewer."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def save_thumbnail(png: Path, out: Path, width: int = 360) -> None:
    with Image.open(png) as im:
        im = im.convert("RGB")
        h = round(im.height * width / im.width)
        im.resize((width, h), Image.LANCZOS).save(out, "JPEG", quality=82, optimize=True)
