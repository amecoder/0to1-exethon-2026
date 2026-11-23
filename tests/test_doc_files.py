from __future__ import annotations
"""11-22: each of the four documents downloads as Markdown, Word (DOCX) and PDF, built from the same document
view; the PDF carries the bundled Korean font and the wireframes as pictures."""

import io
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from PIL import Image
from pypdf import PdfReader

from app.doc_docx import to_docx
from app.doc_fonts import printable
from app.doc_pdf import to_pdf
from app.doc_raster import svg_png
from app.documents import build_documents
from app.wireframe import render_wireframe
from tests.pipeline_helpers import build, to_cp4

DOC_IDS = ("brd", "prd", "screens", "tests")


@pytest.fixture(scope="module")
def docs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parent.parent
    env = tmp_path_factory.mktemp("env") / ".env"
    env.write_text("LINER_API_KEY=test-key-123\nLINER_MODEL=fake-model\n", encoding="utf-8")
    orch, ws, _ = build(repo_root, env)
    to_cp4(orch, ws)
    return build_documents(ws.source)


def tables_in(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for sec in doc["sections"]:
        for block in sec["blocks"]:
            if block["type"] == "table":
                out.append(block)
            elif block["type"] == "screen":
                out += [block["elements"], block["states"]]
    return out


def pdf_text(body: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(body)).pages)


def squeeze(text: str) -> str:
    return "".join(text.split())


def test_a_missing_glyph_becomes_one_the_font_has() -> None:
    assert printable("−①▾ 꽃") == "-1▼ 꽃"
    assert printable("\U0001F33C") == "?"  # an emoji the font cannot draw


@pytest.mark.parametrize("doc_id", DOC_IDS)
def test_docx_has_every_section_and_table(docs: dict[str, Any], doc_id: str) -> None:
    doc = docs[doc_id]
    word = Document(io.BytesIO(to_docx(doc)))
    text = "\n".join(p.text for p in word.paragraphs)
    assert doc["title"] in text
    assert all(sec["title"] in text for sec in doc["sections"])
    expected = tables_in(doc)
    assert len(word.tables) == len(expected)
    for table, block in zip(word.tables, expected):
        assert [c.text for c in table.rows[0].cells] == block["columns"]
        assert len(table.rows) == 1 + len(block["rows"])


def test_docx_screens_carry_the_wireframe_pictures(docs: dict[str, Any]) -> None:
    screens = [b for s in docs["screens"]["sections"] for b in s["blocks"] if b["type"] == "screen"]
    word = Document(io.BytesIO(to_docx(docs["screens"])))
    assert screens and len(word.inline_shapes) == len(screens)


@pytest.mark.parametrize("doc_id", DOC_IDS)
def test_pdf_is_readable_korean_text(docs: dict[str, Any], doc_id: str) -> None:
    doc = docs[doc_id]
    body = to_pdf(doc)
    assert body.startswith(b"%PDF")
    text = squeeze(pdf_text(body))
    assert squeeze(doc["title"]) in text
    assert all(squeeze(sec["title"]) in text for sec in doc["sections"])
    assert all(squeeze(c) in text for t in tables_in(doc) for c in t["columns"])


def test_pdf_turns_wide_tables_sideways(docs: dict[str, Any]) -> None:
    prd = PdfReader(io.BytesIO(to_pdf(docs["prd"]))).pages[0]
    assert float(prd.mediabox.width) > float(prd.mediabox.height)  # PRD has an 11-column table
    brd = PdfReader(io.BytesIO(to_pdf(docs["brd"]))).pages[0]
    assert float(brd.mediabox.width) < float(brd.mediabox.height)


def test_pdf_keeps_every_column_wide_enough() -> None:
    """A real PRD (11-22) has 11 columns where one holds long text; a short column must still fit its letters."""
    long = "고객이 일시정지를 누르면 다음 배송부터 멈추고, 마감이 지난 회차는 그대로 보낸다. " * 6
    doc = {"title": "PRD", "header": {"owner_name": "PM", "version": "v1", "approvals": []}, "summary": [],
           "sections": [{"id": "s", "title": "요구사항", "blocks": [
               {"type": "table", "columns": ["ID", "분류", "이름", "설명", "인수 조건", "예외", "중요도", "상태", "근거",
                                             "관련 요구사항", "관련 화면·테스트"],
                "rows": [["REQ-01", "기능", "일시정지", long, long, long, "상", "확정",
                          long, "REQ-02", long + " 카드번호·유효기간·CVC는"]]}]}]}
    assert squeeze("REQ-01") in squeeze(pdf_text(to_pdf(doc)))


@pytest.mark.parametrize("doc_id", DOC_IDS)
def test_no_page_ends_on_a_section_heading(docs: dict[str, Any], doc_id: str) -> None:
    titles = {squeeze(sec["title"]) for sec in docs[doc_id]["sections"]}
    for page in PdfReader(io.BytesIO(to_pdf(docs[doc_id]))).pages:
        lines = [squeeze(line) for line in (page.extract_text() or "").splitlines() if line.strip()]
        body = [line for line in lines if "/" not in line or not line.replace("/", "").isdigit()]  # drop "2 / 7"
        assert body and body[-1] not in titles


def test_pdf_screens_carry_the_wireframe_pictures(docs: dict[str, Any]) -> None:
    reader = PdfReader(io.BytesIO(to_pdf(docs["screens"])))
    images = sum(len(page.images) for page in reader.pages)
    screens = [b for s in docs["screens"]["sections"] for b in s["blocks"] if b["type"] == "screen"]
    assert images == len(screens) > 0


def test_a_wireframe_becomes_a_png_twice_its_size() -> None:
    screen = {"id": "SCR-01", "title": "홈", "elements": [
        {"no": 1, "kind": "select", "name": "사이즈"}, {"no": 2, "kind": "button", "name": "구독하기"}]}
    svg = render_wireframe(screen)
    png = Image.open(io.BytesIO(svg_png(svg)))
    assert png.format == "PNG" and png.size == (720, int(svg.split('height="')[1].split('"')[0]) * 2)
    darkest = png.convert("L").getextrema()[0]
    assert isinstance(darkest, int) and darkest < 128  # something dark was drawn (the title and the callouts)
