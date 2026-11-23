from __future__ import annotations
"""A wireframe SVG (app/wireframe.py) drawn as a PNG for the Word and PDF documents (11-22).

Word and the PDF library cannot place this SVG with its Korean text, so the same shapes are redrawn with Pillow
and the bundled font. Only what app/wireframe.py writes is drawn: rect (rx), circle, line and text
(font-size, font-weight bold, text-anchor). The SVG is always ours, never outside input.
"""

import io
import xml.etree.ElementTree as ET  # noqa: S405 — parses app/wireframe.py output only
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from app.doc_fonts import BOLD, REGULAR, printable

ANCHORS = {"start": "ls", "middle": "ms", "end": "rs"}  # SVG text y is the baseline


@lru_cache(maxsize=16)
def _font(size: int, bold: bool) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(BOLD if bold else REGULAR), size)


def _num(el: ET.Element, name: str, default: float = 0.0) -> float:
    value = el.get(name)
    return float(value) if value is not None else default


def svg_png(svg: str, scale: int = 2) -> bytes:
    root = ET.fromstring(svg)  # noqa: S314 — our own wireframe markup
    width, height = int(_num(root, "width")), int(_num(root, "height"))
    image = Image.new("RGB", (width * scale, height * scale), "white")
    draw = ImageDraw.Draw(image)
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        fill, stroke = el.get("fill"), el.get("stroke")
        line = scale if stroke else 0
        if tag == "rect":
            x, y = _num(el, "x") * scale, _num(el, "y") * scale
            box = (x, y, x + _num(el, "width") * scale - 1, y + _num(el, "height") * scale - 1)
            draw.rounded_rectangle(box, radius=_num(el, "rx") * scale, fill=fill, outline=stroke, width=line)
        elif tag == "circle":
            cx, cy, r = _num(el, "cx") * scale, _num(el, "cy") * scale, _num(el, "r") * scale
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=stroke, width=line)
        elif tag == "line":
            points = [_num(el, k) * scale for k in ("x1", "y1", "x2", "y2")]
            draw.line(points, fill=stroke or "black", width=scale)
        elif tag == "text":
            font = _font(int(_num(el, "font-size", 12) * scale), el.get("font-weight") == "bold")
            draw.text((_num(el, "x") * scale, _num(el, "y") * scale), printable("".join(el.itertext())),
                      fill=fill or "black", font=font, anchor=ANCHORS.get(el.get("text-anchor", "start"), "ls"))
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
