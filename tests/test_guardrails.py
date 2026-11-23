from __future__ import annotations

import pytest

from app.guardrails import mask_sensitive, scan_sensitive, verify_quote
from app.intake import split_sentences
from tests.flower_script import memo_chunks

SENSITIVE_SAMPLES = [
    ("주민번호는 900101-1234567 입니다", "resident_id", "900101-1234567"),
    ("카드 1234-5678-9012-3456 로 결제", "card", "1234-5678-9012-3456"),
    ("사장님 번호010-1234-5678 로 연락", "phone", "010-1234-5678"),
    ("키는 sk-abcdEFGH1234ijklMNOP5678 입니다", "api_key", "sk-abcdEFGH1234ijklMNOP5678"),
]


@pytest.mark.parametrize(("text", "kind", "raw"), SENSITIVE_SAMPLES)
def test_g3_detects_each_pattern(text: str, kind: str, raw: str) -> None:
    assert kind in {hit.kind for hit in scan_sensitive(text)}


@pytest.mark.parametrize(("text", "kind", "raw"), SENSITIVE_SAMPLES)
def test_g3_mask_removes_raw_value(text: str, kind: str, raw: str) -> None:
    masked = mask_sensitive(text)
    assert raw not in masked
    assert "가림" in masked
    assert scan_sensitive(masked) == ()


def test_g3_flower_memo_has_no_false_positive() -> None:
    assert all(scan_sensitive(chunk) == () for chunk in memo_chunks())


def test_split_sentences_assigns_src_ids_across_chunks() -> None:
    sources = split_sentences(["첫 문장이에요. 둘째 문장!\n\n---\n셋째", "  ", "넷째 문장."])
    assert [s["id"] for s in sources] == ["SRC-01", "SRC-02", "SRC-03", "SRC-04"]
    assert [s["text"] for s in sources] == ["첫 문장이에요.", "둘째 문장!", "셋째", "넷째 문장."]
    assert [s["chunk"] for s in sources] == [1, 1, 1, 3]


def test_split_flower_memo_keeps_text_verbatim() -> None:
    chunks = memo_chunks()
    sources = split_sentences(chunks)
    assert len(sources) >= 15
    assert all(s["text"] in "\n".join(chunks) for s in sources)


TEXTS = {"SRC-01": "배송은 무조건 빨리 해 주세요.", "EV-01": "대부분 3일 안에 재시도한다."}


def test_g1_verbatim_quote_passes() -> None:
    assert verify_quote("무조건 빨리", ["SRC-01"], TEXTS) is True
    assert verify_quote("3일 안에", ["SRC-01", "EV-01"], TEXTS) is True


@pytest.mark.parametrize(("quote", "refs"), [
    ("무조건 신속히", ["SRC-01"]),   # paraphrase, not verbatim
    ("무조건 빨리", []),             # no citation
    ("무조건 빨리", ["SRC-99"]),     # citation that is not stored
    ("", ["SRC-01"]),                # empty quote
])
def test_g1_fails_without_verbatim_cited_quote(quote: str, refs: list[str]) -> None:
    assert verify_quote(quote, refs, TEXTS) is False


def test_normalize_hits_reads_documented_liner_web_search_shape() -> None:
    # Shape from https://liner.com/ko/developers/docs/search-api (2026-11-14 research):
    # results[{title,url,hostname,faviconUrl,description,date}] plus Premium Data `knowledge`.
    from app.agent_runner import normalize_hits

    body = {
        "requestId": "r-1",
        "results": [{
            "title": "구독 결제 실패 처리 가이드",
            "url": "https://example.com/billing",
            "hostname": "example.com",
            "faviconUrl": "https://example.com/favicon.ico",
            "description": "결제가 실패하면 다음 날 한 번 더 시도하는 방식이 흔하다.",
            "date": "2026-10-01",
        }],
        "totalCount": 1,
        "knowledge": [{"title": "t", "description": "d", "sources": [], "dataAsOf": "2026-11", "columns": [], "rows": []}],
    }
    assert normalize_hits(body) == [{
        "url": "https://example.com/billing",
        "title": "구독 결제 실패 처리 가이드",
        "snippet": "결제가 실패하면 다음 날 한 번 더 시도하는 방식이 흔하다.",
        "date": "2026-10-01",
        "via": "search",
    }]
