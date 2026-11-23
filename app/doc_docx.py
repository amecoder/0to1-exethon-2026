from __future__ import annotations
"""A document view as a Word file (11-22), from the same blocks as the Markdown and the print HTML.

Word draws the text with a font installed on the reader's computer (맑은 고딕 on Windows, a Korean system font
elsewhere); wireframes go in as PNG pictures (app/doc_raster.py).
"""

import io
from collections.abc import Mapping, Sequence
from typing import Any

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from app.doc_layout import EMPTY_ROWS, cover_lines, is_wide, warning_lines
from app.doc_raster import svg_png

FONT = "Malgun Gothic"
FONT_KO = "맑은 고딕"
GREY = RGBColor(0x66, 0x66, 0x66)
PICTURE_WIDTH = Mm(75)


def to_docx(doc: Mapping[str, Any]) -> bytes:
    word = Document()
    _setup(word, sideways=is_wide(doc))
    word.add_heading(str(doc["title"]), level=0)
    for line in cover_lines(doc):
        _small(word, line)
    word.add_heading("한눈에 보기", level=1)
    for line in doc.get("summary") or ["(아직 요약이 없습니다)"]:
        word.add_paragraph(str(line))
    for sec in doc["sections"]:
        word.add_heading(str(sec["title"]), level=1)
        for block in sec["blocks"]:
            _block(word, block)
    warnings = warning_lines(doc)
    if warnings:
        word.add_heading(f"검사 경고 ({len(warnings)})", level=1)
        for line in warnings:
            word.add_paragraph(line, style="List Bullet")
    out = io.BytesIO()
    word.save(out)
    return out.getvalue()


def _setup(word: DocxDocument, sideways: bool) -> None:
    section = word.sections[0]
    section.page_width, section.page_height = (Mm(297), Mm(210)) if sideways else (Mm(210), Mm(297))
    section.orientation = WD_ORIENT.LANDSCAPE if sideways else WD_ORIENT.PORTRAIT
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Mm(18))
    for name in ("Normal", "Title", "Heading 1", "Heading 2", "List Bullet"):
        style = word.styles[name]
        style.font.name = FONT
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        fonts.set(qn("w:eastAsia"), FONT_KO)
    word.styles["Normal"].font.size = Pt(10)


def _small(word: DocxDocument, text: str) -> None:
    run = word.add_paragraph().add_run(text)
    run.font.size, run.font.color.rgb = Pt(8.5), GREY


def _block(word: DocxDocument, block: Mapping[str, Any]) -> None:
    kind = block["type"]
    if kind == "paragraph":
        word.add_paragraph(str(block["text"]))
    elif kind == "list":
        for item in block["items"]:
            word.add_paragraph(str(item), style="List Bullet")
    elif kind == "table":
        _table(word, block)
    elif kind == "screen":
        word.add_picture(io.BytesIO(svg_png(block["svg"])), width=PICTURE_WIDTH)
        if block.get("purpose"):
            word.add_paragraph(f"목적: {block['purpose']}")
        _table(word, block["elements"])
        _table(word, block["states"])
    else:
        raise ValueError(f"unknown block type: {kind}")


def _table(word: DocxDocument, block: Mapping[str, Any]) -> None:
    columns: Sequence[str] = block["columns"]
    rows: Sequence[Sequence[str]] = block["rows"]
    table = word.add_table(rows=1 + len(rows), cols=len(columns))
    table.style = "Table Grid"
    for cell, name in zip(table.rows[0].cells, columns):
        cell.text = str(name)
        for run in cell.paragraphs[0].runs:
            run.font.bold = True
    _repeat_header(table.rows[0])
    for row, values in zip(table.rows[1:], rows):
        for cell, value in zip(row.cells, values):
            cell.text = str(value)
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)
    if not rows:
        word.add_paragraph(EMPTY_ROWS)
    word.add_paragraph()


def _repeat_header(row: Any) -> None:
    """The header row repeats at the top of every page the table runs over."""
    mark = OxmlElement("w:tblHeader")
    mark.set(qn("w:val"), "true")
    row._tr.get_or_add_trPr().append(mark)
