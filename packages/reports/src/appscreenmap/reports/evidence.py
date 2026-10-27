"""Evidence shots: a crop of the full screenshot around one failing element, outlined so the reader sees what to fix.

Shared by every format: Markdown copies the file, HTML / PDF inline it, DOCX embeds it.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

WIDTH = 360  # px: sharp at the size the reports show it (about 2 in on paper)
# Mirrors tokens.css --bad (#ff5d5d): an image can't read CSS variables. The caption carries the word.
OUTLINE = (255, 93, 93)
KEYLINE = (10, 10, 10)  # --bg


def crop(run: Path, shot: str | None, bounds: list[int] | None) -> bytes | None:
    """JPEG bytes of the element's surroundings with the element outlined, or None when it can't be drawn."""
    if not shot or not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        return None
    try:
        with Image.open(Path(run) / shot) as src:
            im = src.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    try:
        x1, y1, x2, y2 = (int(v) for v in bounds)
    except (TypeError, ValueError, OverflowError):  # json.load reads Infinity / NaN
        return None
    # Off the image (a scrolled-off carousel item): a crop would point at nothing.
    if x2 <= x1 or y2 <= y1 or x1 >= im.width or y1 >= im.height or x2 <= 0 or y2 <= 0:
        return None
    # Enough context to recognise the screen, never so much the element gets lost.
    pad = max(160, (x2 - x1) // 2, (y2 - y1) // 2)
    box = (max(0, x1 - pad), max(0, y1 - pad), min(im.width, x2 + pad), min(im.height, y2 + pad))
    out = im.crop(box)
    out.thumbnail((WIDTH, WIDTH * 2))
    # Outline drawn at output size so it stays 3 px, with a dark keyline so it reads on any app colour (WCAG 1.4.11).
    k = out.width / (box[2] - box[0])
    r = [(x1 - box[0]) * k, (y1 - box[1]) * k, (x2 - box[0]) * k, (y2 - box[1]) * k]
    draw = ImageDraw.Draw(out)
    draw.rectangle([r[0] - 4, r[1] - 4, r[2] + 4, r[3] + 4], outline=KEYLINE, width=1)
    draw.rectangle([r[0] - 3, r[1] - 3, r[2] + 3, r[3] + 3], outline=OUTLINE, width=3)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=82)
    return buf.getvalue()
