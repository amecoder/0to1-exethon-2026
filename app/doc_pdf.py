from __future__ import annotations
"""A document view as a PDF file (11-22), from the same blocks as the Markdown and the print HTML.

The bundled Nanum Gothic (app/doc_fonts.py) is embedded, so the file reads the same on any computer. A document
with a wide table (more than WIDE_COLUMNS columns) is laid out on sideways A4 pages.
"""

import io
import re
from collections.abc import Mapping, Sequence
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from app.doc_fonts import BOLD, FAMILY, REGULAR, printable
from app.doc_layout import EMPTY_ROWS, cover_lines, is_wide, warning_lines
from app.doc_raster import svg_png

LINE = 5.5  # mm per text line at 10 pt
PICTURE_WIDTH = 75  # mm
HEAD_FILL = (238, 238, 238)
GREY = (102, 102, 102)
MIN_WEIGHT, MAX_WEIGHT = 4, 40  # 제안: a column's share follows its average text length, within these bounds
KEEP_WITH_NEXT = 35  # mm a heading needs below it, or it starts the next page
HEAD_SIZE = 8.5  # pt, table text
PADDING = 1.2  # mm inside each cell
MIN_COLUMN, MAX_FLOOR = 10, 30  # 제안 (mm): every column gets at least MIN_COLUMN; a long word claims at most MAX_FLOOR


class _Pdf(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(FAMILY, size=8)
        self.set_text_color(*GREY)
        self.cell(0, 8, f"{self.page_no()} / {{nb}}", align="C")


def to_pdf(doc: Mapping[str, Any]) -> bytes:
    pdf = _Pdf(orientation="L" if is_wide(doc) else "P", format="A4")
    pdf.add_font(FAMILY, "", str(REGULAR))
    pdf.add_font(FAMILY, "B", str(BOLD))
    pdf.set_title(printable(str(doc["title"])))
    pdf.set_auto_page_break(True, margin=16)
    pdf.set_margins(16, 16, 16)
    pdf.add_page()
    _heading(pdf, str(doc["title"]), 17)
    pdf.set_text_color(*GREY)
    for line in cover_lines(doc):
        _text(pdf, line, 8.5)
    pdf.set_text_color(0, 0, 0)
    _heading(pdf, "한눈에 보기", 13)
    for line in doc.get("summary") or ["(아직 요약이 없습니다)"]:
        _text(pdf, str(line))
    for sec in doc["sections"]:
        _heading(pdf, str(sec["title"]), 13, _room(sec["blocks"][0]) if sec["blocks"] else KEEP_WITH_NEXT)
        for block in sec["blocks"]:
            _block(pdf, block)
    warnings = warning_lines(doc)
    if warnings:
        _heading(pdf, f"검사 경고 ({len(warnings)})", 13)
        for line in warnings:
            _text(pdf, f"• {line}")
    return bytes(pdf.output())


def _room(block: Mapping[str, Any]) -> float:
    """mm the start of a block needs right under its heading: a wireframe picture moves whole."""
    if block["type"] == "screen":
        width, height = (float(v) for v in re.findall(r'(?:width|height)="([\d.]+)"', block["svg"])[:2])
        return PICTURE_WIDTH * height / width + 6
    return KEEP_WITH_NEXT


def _heading(pdf: FPDF, text: str, size: float, keep: float = KEEP_WITH_NEXT) -> None:
    own = 2 + size * 0.5 + 1.5  # the heading's own height (one line)
    if pdf.get_y() + own + keep > pdf.page_break_trigger:
        pdf.add_page()  # a heading does not stay alone at the foot of a page
    pdf.ln(2)
    pdf.set_font(FAMILY, "B", size)
    pdf.multi_cell(0, size * 0.5, printable(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1.5)


def _text(pdf: FPDF, text: str, size: float = 10) -> None:
    pdf.set_font(FAMILY, "", size)
    pdf.multi_cell(0, LINE * size / 10, printable(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)


def _block(pdf: FPDF, block: Mapping[str, Any]) -> None:
    kind = block["type"]
    if kind == "paragraph":
        _text(pdf, str(block["text"]))
    elif kind == "list":
        for item in block["items"]:
            _text(pdf, f"• {item}")
    elif kind == "table":
        _table(pdf, block)
    elif kind == "screen":
        pdf.image(io.BytesIO(svg_png(block["svg"])), w=PICTURE_WIDTH)
        pdf.ln(2)
        if block.get("purpose"):
            _text(pdf, f"목적: {block['purpose']}")
        _table(pdf, block["elements"])
        _table(pdf, block["states"])
    else:
        raise ValueError(f"unknown block type: {kind}")


def _weights(columns: Sequence[str], rows: Sequence[Sequence[str]]) -> list[float]:
    out = []
    for n, name in enumerate(columns):
        texts = [str(name), *(str(r[n]) for r in rows if n < len(r))]
        out.append(min(max(sum(len(t) for t in texts) / len(texts), MIN_WEIGHT), MAX_WEIGHT))
    return out


def _widths(pdf: FPDF, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> tuple[float, ...]:
    """Column widths in mm: first room for the longest word of each column (header in bold), then the rest of
    the page width shared by average text length. Without the floor a short column next to long ones shrank
    below one letter (a real PRD, 11-22)."""
    floors = []
    for n, name in enumerate(columns):
        pdf.set_font(FAMILY, "B", HEAD_SIZE)
        widest = max((pdf.get_string_width(printable(w)) for w in str(name).split()), default=0.0)
        pdf.set_font(FAMILY, "", HEAD_SIZE)
        for r in rows:
            if n < len(r):
                widest = max([widest, *(pdf.get_string_width(printable(w)) for w in str(r[n]).split())])
        floors.append(min(max(widest + 2 * PADDING + 1, MIN_COLUMN), MAX_FLOOR))
    room = pdf.epw - sum(floors)
    if room <= 0:
        return tuple(f * pdf.epw / sum(floors) for f in floors)
    weights = _weights(columns, rows)
    return tuple(f + room * w / sum(weights) for f, w in zip(floors, weights))


def _table(pdf: FPDF, block: Mapping[str, Any]) -> None:
    columns: Sequence[str] = block["columns"]
    rows: Sequence[Sequence[str]] = block["rows"]
    widths = _widths(pdf, columns, rows)
    pdf.set_font(FAMILY, "", HEAD_SIZE)
    head = FontFace(emphasis="BOLD", fill_color=HEAD_FILL)
    with pdf.table(col_widths=widths, headings_style=head, line_height=4.6,  # type: ignore[arg-type]
                   text_align="LEFT", repeat_headings=1, padding=PADDING) as table:
        heading = table.row()
        for name in columns:
            heading.cell(printable(str(name)))
        for values in rows:
            row = table.row()
            for n in range(len(columns)):
                row.cell(printable(str(values[n])) if n < len(values) else "")
    if not rows:
        _text(pdf, EMPTY_ROWS, 9)
    pdf.ln(3)
