from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.doc_html import html_documents, table_html, text
from app.documents import build_documents
from app.export import DOC_FILES, build_bundle, marked_items
from tests.pipeline_helpers import build, to_cp4

HTML_FILES = {"BRD.html", "PRD.html", "화면설계서.html", "테스트케이스.html", "index.html"}


@pytest.fixture(scope="module")
def approved_source(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parent.parent
    env = tmp_path_factory.mktemp("env") / ".env"
    env.write_text("LINER_API_KEY=test-key-123\nLINER_MODEL=fake-model\n", encoding="utf-8")
    orch, ws, _ = build(repo_root, env)
    to_cp4(orch, ws)
    orch.confirm("CP4", True, "발주사")
    return ws.source


def outside_refs(html: str) -> list[str]:
    """Anything that would make the browser fetch something (SVG namespaces are not requests)."""
    found = re.findall(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//[^"'\s>]+|url\(\s*["']?(?:https?:)?//|@import|<script|<link""",
                       html, re.I)
    return found


def test_ids_become_chips_and_text_is_escaped() -> None:
    assert text("<b>REQ-01</b>") == '&lt;b&gt;<span class="id">REQ-01</span>&lt;/b&gt;'


def test_status_column_gets_badges_and_marked_rows() -> None:
    html = table_html({"columns": ["ID", "이름", "상태"], "rows": [["REQ-01", "a", "가정"], ["REQ-02", "b", "확정"]]})
    assert '<tr class="marked">' in html and html.count("<tr>") == 2  # header row + the confirmed row
    assert '<span class="badge warn">가정</span>' in html and '<span class="badge ok">확정</span>' in html
    assert table_html({"columns": ["a"], "rows": []}) == '<p class="empty">항목이 없습니다</p>'


def test_every_document_is_a_self_contained_print_page(approved_source: dict[str, Any]) -> None:
    docs = build_documents(approved_source)
    marked = {**marked_items(approved_source), "가정": ["REQ-01 배송 요일"]}
    files = html_documents(docs, DOC_FILES, marked, "꽃님 정기구독", "2026-11-16T00:00:00+00:00")
    assert set(files) == HTML_FILES
    for name, html in files.items():
        assert html.startswith("<!doctype html>") and html.endswith("</html>")
        assert outside_refs(html) == [], name
        assert "size: A4" in html and "@media print" in html and "counter(page)" in html
    brd = files["BRD.html"]
    assert 'class="meta"' in brd and "승인됨" in brd and docs["brd"]["header"]["owner_name"] in brd
    for sec in docs["brd"]["sections"]:  # table of contents points at real anchors
        assert f'href="#{sec["id"]}"' in brd and f'id="{sec["id"]}"' in brd
    assert "<thead>" in files["PRD.html"] and "아직 확정되지 않은 항목" in brd
    assert files["화면설계서.html"].count("<svg") == len(approved_source["screens"])
    assert 'href="BRD.html"' in files["index.html"] and 'href="prototype.html"' in files["index.html"]


def test_bundle_carries_html_next_to_markdown(approved_source: dict[str, Any]) -> None:
    zf = zipfile.ZipFile(io.BytesIO(build_bundle(approved_source, project="꽃님 정기구독")))
    names = set(zf.namelist())
    assert HTML_FILES <= names and {"BRD.md", "PRD.md"} <= names
    assert "꽃님 정기구독" in zf.read("index.html").decode("utf-8")
    assert "index.html" in zf.read("README.txt").decode("utf-8")
